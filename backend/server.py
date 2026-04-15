import os
import struct
import time
import sqlite3
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

import paho.mqtt.client as mqtt

# CONFIG
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC = "esp32/image"

DB_NAME = "camerasensor.db"
IMAGE_DIR = "received"

os.makedirs(IMAGE_DIR, exist_ok=True)


# LIFESPAN HANDLER
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    thread = threading.Thread(target=mqtt_thread)
    thread.daemon = True
    thread.start()
    yield
    # Shutdown


app = FastAPI(lifespan=lifespan)
app.mount("/images", StaticFiles(directory=IMAGE_DIR), name="images")


# WEBSOCKET MANAGER
class ConnectionManager:
    def __init__(self):
        self.active_connections = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)


manager = ConnectionManager()


# DB
def init_db():
    """Initialize database and create tables if they don't exist"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        test_group INTEGER,
        timestamp_sent INTEGER,
        timestamp_received INTEGER,
        latency_ms REAL,
        image_path TEXT
    )
    """
    )

    conn.commit()
    conn.close()


def store_metadata(ts_sent, ts_recv, latency, path):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
    INSERT INTO images (timestamp_sent, timestamp_received, latency_ms, image_path)
    VALUES (?, ?, ?, ?)
    """,
        (ts_sent, ts_recv, latency, path),
    )

    conn.commit()
    conn.close()


# MQTT HANDLER
def on_message(client, userdata, msg):
    try:
        recv_time = int(time.time() * 1_000_000)

        ts_sent = struct.unpack("<Q", msg.payload[0:8])[0]
        img_size = struct.unpack("<I", msg.payload[8:12])[0]
        img_data = msg.payload[12 : 12 + img_size]

        latency = (recv_time - ts_sent) / 1000.0

        filename = f"{recv_time}.jpg"
        path = os.path.join(IMAGE_DIR, filename)

        with open(path, "wb") as f:
            f.write(img_data)

        store_metadata(ts_sent, recv_time, latency, path)

        # Push to frontend (async)
        import asyncio

        asyncio.run(
            manager.broadcast(
                {
                    "image_url": f"/images/{filename}",
                    "latency": latency,
                    "timestamp": recv_time,
                }
            )
        )

    except Exception as e:
        print("Error:", e)


def mqtt_thread():
    client = mqtt.Client()
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.subscribe(MQTT_TOPIC)
    client.on_message = on_message
    client.loop_forever()


# WEBSOCKET
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    try:
        while True:
            await websocket.receive_text()  # keep alive
    except WebSocketDisconnect:
        manager.disconnect(websocket)
