"""
subscriber.py -- Level 2 CLI Subscriber
========================================
Standalone MQTT subscriber for debugging.
Receives motion-detected frames, saves them, and prints statistics.
"""

import os
import struct
import time
import sqlite3

import paho.mqtt.client as mqtt

# CONFIG
MQTT_BROKER = "192.168.1.11"
MQTT_PORT = 1883
MQTT_TOPIC = "esp32/image"

DB_NAME = "camerasensor.db"
IMAGE_DIR = "received"

# Global state
latencies = []
recv_timestamps = []
total_received = 0
frame_indices = []

HEADER_FMT = "<QHHI"  # ts_sent_us, test_group, sequence_in_test, image_size
HEADER_SIZE = struct.calcsize(HEADER_FMT)

os.makedirs(IMAGE_DIR, exist_ok=True)


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
    conn.commit()
    conn.close()


def parse_packet(payload: bytes):
    if len(payload) < HEADER_SIZE:
        raise ValueError("Payload too small")

    timestamp_sent, test_group, sequence_in_test, image_size = struct.unpack(
        HEADER_FMT, payload[0:HEADER_SIZE]
    )

    image_data = payload[HEADER_SIZE : HEADER_SIZE + image_size]
    if len(image_data) != image_size:
        raise ValueError("Image size mismatch")

    return timestamp_sent, test_group, sequence_in_test, image_data


def save_image(image_data, timestamp_received):
    filename = f"{timestamp_received}.jpg"
    path = os.path.join(IMAGE_DIR, filename)
    with open(path, "wb") as f:
        f.write(image_data)
    return path


def store_metadata(timestamp_sent, timestamp_received, latency_ms, frame_idx, image_path):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        """
    INSERT INTO images (test_group, sequence_in_test, timestamp_sent,
                        timestamp_received, latency_ms, image_path)
    VALUES (0, ?, ?, ?, ?, ?)
    """,
        (frame_idx, timestamp_sent, timestamp_received, latency_ms, image_path),
    )
    conn.commit()
    conn.close()


def on_connect(client, userdata, flags, rc):
    print(f"[MQTT] Connected with result code {rc}")
    client.subscribe(MQTT_TOPIC)


def on_message(client, userdata, msg):
    try:
        global total_received

        recv_time_us = time.time_ns() // 1000

        timestamp_sent, test_group, sequence_in_test, image_data = parse_packet(
            msg.payload
        )

        latency_ms = max(0.0, (recv_time_us - timestamp_sent) / 1000.0)

        latencies.append(latency_ms)
        recv_timestamps.append(recv_time_us)
        frame_indices.append(sequence_in_test)
        total_received += 1

        image_path = save_image(image_data, recv_time_us)
        store_metadata(timestamp_sent, recv_time_us, latency_ms, sequence_in_test, image_path)

        print(
            f"[MOTION] frame={sequence_in_test} | "
            f"latency={latency_ms:.2f} ms | "
            f"saved: {image_path}"
        )

    except Exception as e:
        print(f"[ERROR] {e}")


def compute_intervals():
    intervals = []
    for i in range(1, len(recv_timestamps)):
        dt = (recv_timestamps[i] - recv_timestamps[i - 1]) / 1_000_000
        intervals.append(dt)
    return intervals


def print_summary():
    print("\n===== SESSION SUMMARY =====")

    if not latencies:
        print("No data received")
        return

    avg_latency = sum(latencies) / len(latencies)
    min_latency = min(latencies)
    max_latency = max(latencies)

    intervals = compute_intervals()
    avg_interval = sum(intervals) / len(intervals) if intervals else 0

    print(f"Total Received   : {total_received}")
    print(f"Motion frames    : {len(set(frame_indices))} unique frame indices")

    print("\nLatency (ms):")
    print(f"  Avg            : {avg_latency:.2f}")
    print(f"  Min            : {min_latency:.2f}")
    print(f"  Max            : {max_latency:.2f}")

    print("\nInterval (sec):")
    print(f"  Avg Interval   : {avg_interval:.2f}")

    print("===========================\n")


def main():
    init_db()

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_BROKER, MQTT_PORT, 60)

    print("[SYSTEM] Level 2 subscriber started (motion detection mode)...")
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[INFO] Stopping subscriber...")
        print_summary()


if __name__ == "__main__":
    main()
