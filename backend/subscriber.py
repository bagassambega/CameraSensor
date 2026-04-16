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

EXPECTED_TOTAL = 130  # 10 + 20 + 100
HEADER_FMT = "<QHHI"  # ts_sent_us, test_group, sequence_in_test, image_size
HEADER_SIZE = struct.calcsize(HEADER_FMT)

# Ensure directory exists
os.makedirs(IMAGE_DIR, exist_ok=True)


# DATABASE SETUP
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp_sent INTEGER,
        timestamp_received INTEGER,
        latency_ms REAL,
        image_path TEXT
    )
    """
    )

    conn.commit()
    conn.close()


# PACKET PARSER
def parse_packet(payload: bytes):
    """
    Parse binary packet:
    [8 bytes timestamp][2 bytes test_group][2 bytes sequence][4 bytes size][image]
    """
    if len(payload) < HEADER_SIZE:
        raise ValueError("Payload too small")

    timestamp_sent, test_group, sequence_in_test, image_size = struct.unpack(
        HEADER_FMT, payload[0:HEADER_SIZE]
    )

    image_data = payload[HEADER_SIZE : HEADER_SIZE + image_size]

    if len(image_data) != image_size:
        raise ValueError("Image size mismatch")

    return timestamp_sent, test_group, sequence_in_test, image_data


# SAVE IMAGE
def save_image(image_data, timestamp_received):
    filename = f"{timestamp_received}.jpg"
    path = os.path.join(IMAGE_DIR, filename)

    with open(path, "wb") as f:
        f.write(image_data)

    return path


# STORE METADATA
def store_metadata(timestamp_sent, timestamp_received, latency_ms, image_path):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
    INSERT INTO images (timestamp_sent, timestamp_received, latency_ms, image_path)
    VALUES (?, ?, ?, ?)
    """,
        (timestamp_sent, timestamp_received, latency_ms, image_path),
    )

    conn.commit()
    conn.close()


# MQTT CALLBACKS
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

        total_received += 1

        # Save image
        image_path = save_image(image_data, recv_time_us)

        # Store to DB
        store_metadata(timestamp_sent, recv_time_us, latency_ms, image_path)

        print(f"[RECV] N={test_group} seq={sequence_in_test} image saved: {image_path}")
        print(f"[INFO] Latency: {latency_ms:.2f} ms")

    except Exception as e:
        print(f"[ERROR] {e}")


# Interval calculation
def compute_intervals():
    intervals = []
    for i in range(1, len(recv_timestamps)):
        dt = (recv_timestamps[i] - recv_timestamps[i - 1]) / 1_000_000
        intervals.append(dt)
    return intervals


# Summary
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

    packet_loss = EXPECTED_TOTAL - total_received

    print(f"Total Received   : {total_received}")
    print(f"Expected         : {EXPECTED_TOTAL}")
    print(f"Packet Loss      : {packet_loss}")

    print("\nLatency (ms):")
    print(f"  Avg            : {avg_latency:.2f}")
    print(f"  Min            : {min_latency:.2f}")
    print(f"  Max            : {max_latency:.2f}")

    print("\nInterval (sec):")
    print(f"  Avg Interval   : {avg_interval:.2f}")

    print("===========================\n")


# MAIN
def main():
    init_db()

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_BROKER, MQTT_PORT, 60)

    print("[SYSTEM] Subscriber started...")
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[INFO] Stopping subscriber...")
        print_summary()


if __name__ == "__main__":
    main()
