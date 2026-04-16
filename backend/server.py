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
MQTT_BROKER = "192.168.1.11"
MQTT_PORT = 1883
MQTT_TOPIC = "esp32/image"

DB_NAME = "camerasensor.db"
IMAGE_DIR = "received"

EXPECTED_TOTAL = 130  # Total expected images
EXPECTED_TEST_GROUPS = (10, 20, 100)

os.makedirs(IMAGE_DIR, exist_ok=True)

# Global state for statistics
latencies = []
recv_timestamps = []
total_received = 0
latencies_by_test = {n: [] for n in EXPECTED_TEST_GROUPS}
recv_timestamps_by_test = {n: [] for n in EXPECTED_TEST_GROUPS}
recv_intervals_by_test = {n: [] for n in EXPECTED_TEST_GROUPS}

HEADER_FMT = "<QHHI"  # ts_sent_us, test_group, sequence_in_test, image_size
HEADER_SIZE = struct.calcsize(HEADER_FMT)


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
        sequence_in_test INTEGER,
        timestamp_sent INTEGER,
        timestamp_received INTEGER,
        latency_ms REAL,
        sent_interval_s REAL,
        image_path TEXT
    )
    """
    )

    existing_columns = {
        row[1] for row in cursor.execute("PRAGMA table_info(images)").fetchall()
    }

    if "test_group" not in existing_columns:
        cursor.execute("ALTER TABLE images ADD COLUMN test_group INTEGER")
    if "sequence_in_test" not in existing_columns:
        cursor.execute("ALTER TABLE images ADD COLUMN sequence_in_test INTEGER")
    if "sent_interval_s" not in existing_columns:
        cursor.execute("ALTER TABLE images ADD COLUMN sent_interval_s REAL")

    conn.commit()
    conn.close()


def store_metadata(
    test_group, sequence_in_test, ts_sent, ts_recv, latency, sent_interval, path
):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
    INSERT INTO images (
        test_group,
        sequence_in_test,
        timestamp_sent,
        timestamp_received,
        latency_ms,
        sent_interval_s,
        image_path
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (test_group, sequence_in_test, ts_sent, ts_recv, latency, sent_interval, path),
    )

    conn.commit()
    conn.close()


# STATISTICS
def compute_intervals():
    """Calculate time intervals between received images"""
    intervals = []
    for i in range(1, len(recv_timestamps)):
        dt = (recv_timestamps[i] - recv_timestamps[i - 1]) / 1_000_000
        intervals.append(dt)
    return intervals


def get_statistics():
    """Compute current session statistics"""
    if not latencies:
        return {
            "total_received": 0,
            "expected": EXPECTED_TOTAL,
            "packet_loss": EXPECTED_TOTAL,
            "avg_latency": 0,
            "min_latency": 0,
            "max_latency": 0,
            "avg_interval": 0,
        }

    recv_intervals = compute_intervals()
    recv_intervals = [
        interval
        for n in EXPECTED_TEST_GROUPS
        for interval in recv_intervals_by_test.get(n, [])
    ]

    by_test = {}
    for n in EXPECTED_TEST_GROUPS:
        test_latencies = latencies_by_test.get(n, [])
        test_recv_intervals = recv_intervals_by_test.get(n, [])
        by_test[str(n)] = {
            "received": len(test_latencies),
            "expected": n,
            "packet_loss": max(0, n - len(test_latencies)),
            "avg_latency": (
                (sum(test_latencies) / len(test_latencies)) if test_latencies else 0
            ),
            "avg_interval": (
                (sum(test_recv_intervals) / len(test_recv_intervals))
                if test_recv_intervals
                else 0
            ),
        }

    return {
        "total_received": total_received,
        "expected": EXPECTED_TOTAL,
        "packet_loss": max(0, EXPECTED_TOTAL - total_received),
        "avg_latency": sum(latencies) / len(latencies),
        "min_latency": min(latencies),
        "max_latency": max(latencies),
        "avg_interval": (
            sum(recv_intervals) / len(recv_intervals) if recv_intervals else 0
        ),
        "by_test": by_test,
    }


def parse_packet(payload):
    if len(payload) < HEADER_SIZE:
        raise ValueError("Payload too short for packet header")

    ts_sent_us, test_group, sequence_in_test, img_size = struct.unpack(
        HEADER_FMT, payload[:HEADER_SIZE]
    )

    expected_size = HEADER_SIZE + img_size
    if len(payload) < expected_size:
        raise ValueError("Image payload is incomplete")

    image_data = payload[HEADER_SIZE:expected_size]
    return ts_sent_us, test_group, sequence_in_test, image_data


# MQTT HANDLER
def on_message(client, userdata, msg):
    try:
        recv_time = time.time_ns() // 1000

        ts_sent, test_group, sequence_in_test, img_data = parse_packet(msg.payload)

        if test_group not in latencies_by_test:
            latencies_by_test[test_group] = []
            recv_timestamps_by_test[test_group] = []
            recv_intervals_by_test[test_group] = []

        latency = max(0.0, (recv_time - ts_sent) / 1000.0)

        recv_interval = None
        if recv_timestamps_by_test[test_group]:
            delta_us = recv_time - recv_timestamps_by_test[test_group][-1]
            if delta_us >= 0:
                recv_interval = delta_us / 1_000_000
                recv_intervals_by_test[test_group].append(recv_interval)

        recv_timestamps_by_test[test_group].append(recv_time)

        filename = f"{recv_time}.jpg"
        path = os.path.join(IMAGE_DIR, filename)

        with open(path, "wb") as f:
            f.write(img_data)

        store_metadata(
            test_group,
            sequence_in_test,
            ts_sent,
            recv_time,
            latency,
            recv_interval,
            path,
        )

        # Push to frontend (async)
        import asyncio

        global total_received
        latencies.append(latency)
        latencies_by_test[test_group].append(latency)
        recv_timestamps.append(recv_time)
        total_received += 1

        stats = get_statistics()

        asyncio.run(
            manager.broadcast(
                {
                    "image_url": f"/images/{filename}",
                    "latency": latency,
                    "timestamp": recv_time,
                    "timestamp_sent": ts_sent,
                    "test_group": test_group,
                    "sequence_in_test": sequence_in_test,
                    "recv_interval_s": recv_interval,
                    "stats": stats,
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
