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
MQTT_BROKER = "10.134.67.51"
MQTT_PORT = 1883
MQTT_TOPIC = "esp32/image"

DB_NAME = "camerasensor.db"
IMAGE_DIR = "received"

os.makedirs(IMAGE_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------
latencies = []
recv_timestamps = []
recv_intervals = []
total_received = 0  # Total motion-detected frames received
frame_indices = []  # Track which video frame indices had motion

HEADER_FMT = "<QHHI"  # ts_sent_us, test_group, sequence_in_test, image_size
HEADER_SIZE = struct.calcsize(HEADER_FMT)
MAX_VALID_LATENCY_MS = 30_000.0


def normalize_sender_timestamp_us(ts_sent_raw: int, recv_time_us: int):
    """Normalize sender timestamp to microseconds.

    Accepts sender timestamps in seconds/ms/us/ns and converts to us.
    Returns None when the value cannot be interpreted safely.
    """
    if ts_sent_raw <= 0:
        return None

    # Seconds since epoch
    if ts_sent_raw < 10**11:
        ts_us = ts_sent_raw * 1_000_000
    # Milliseconds since epoch
    elif ts_sent_raw < 10**14:
        ts_us = ts_sent_raw * 1_000
    # Microseconds since epoch
    elif ts_sent_raw < 10**17:
        ts_us = ts_sent_raw
    # Nanoseconds since epoch
    elif ts_sent_raw < 10**20:
        ts_us = ts_sent_raw // 1_000
    else:
        return None

    # Reject clock jump or corrupt packet
    if ts_us > recv_time_us + 5_000_000:
        return None

    return ts_us


# ---------------------------------------------------------------------------
# Lifespan handler
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    thread = threading.Thread(target=mqtt_thread)
    thread.daemon = True
    thread.start()
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/images", StaticFiles(directory=IMAGE_DIR), name="images")


# ---------------------------------------------------------------------------
# WebSocket manager
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def init_db():
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

    # Ensure all columns exist
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
        test_group, sequence_in_test,
        timestamp_sent, timestamp_received,
        latency_ms, sent_interval_s, image_path
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (test_group, sequence_in_test, ts_sent, ts_recv, latency, sent_interval, path),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
def get_statistics():
    if not latencies:
        return {
            "total_received": 0,
            "avg_latency": 0,
            "min_latency": 0,
            "max_latency": 0,
            "avg_interval": 0,
            "motion_frames": [],
        }

    return {
        "total_received": total_received,
        "avg_latency": sum(latencies) / len(latencies),
        "min_latency": min(latencies),
        "max_latency": max(latencies),
        "avg_interval": (
            sum(recv_intervals) / len(recv_intervals) if recv_intervals else 0
        ),
        # Send the last 20 frame indices to show the motion event timeline
        "motion_frames": frame_indices[-20:],
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


# ---------------------------------------------------------------------------
# MQTT handler
# ---------------------------------------------------------------------------
def on_message(client, userdata, msg):
    try:
        recv_time = time.time_ns() // 1000

        ts_sent_raw, test_group, sequence_in_test, img_data = parse_packet(msg.payload)

        ts_sent = normalize_sender_timestamp_us(ts_sent_raw, recv_time)
        latency = None
        if ts_sent is not None:
            candidate_latency = (recv_time - ts_sent) / 1000.0
            if 0.0 <= candidate_latency <= MAX_VALID_LATENCY_MS:
                latency = candidate_latency

        latency_for_payload = latency if latency is not None else 0.0

        # Compute receive interval
        recv_interval = None
        if recv_timestamps:
            delta_us = recv_time - recv_timestamps[-1]
            if delta_us >= 0:
                recv_interval = delta_us / 1_000_000
                recv_intervals.append(recv_interval)

        # Save image
        filename = f"{recv_time}.jpg"
        path = os.path.join(IMAGE_DIR, filename)
        with open(path, "wb") as f:
            f.write(img_data)

        store_metadata(
            test_group,
            sequence_in_test,
            ts_sent if ts_sent is not None else ts_sent_raw,
            recv_time,
            latency_for_payload,
            recv_interval,
            path,
        )

        # Update global state
        global total_received
        if latency is not None:
            latencies.append(latency)
        recv_timestamps.append(recv_time)
        frame_indices.append(sequence_in_test)
        total_received += 1

        stats = get_statistics()

        # Push to frontend
        import asyncio

        asyncio.run(
            manager.broadcast(
                {
                    "image_url": f"/images/{filename}",
                    "latency": latency_for_payload,
                    "timestamp": recv_time,
                    "timestamp_sent": ts_sent,
                    "frame_index": sequence_in_test,
                    "motion_detected": True,
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


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
