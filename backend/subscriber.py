import os
import struct
import time
import sqlite3

import paho.mqtt.client as mqtt

# ===== CONFIG =====
MQTT_BROKER = "192.168.1.11"
MQTT_PORT = 1883
MQTT_TOPIC = "esp32/image"

DB_NAME = "camerasensor.db"
IMAGE_DIR = "received"

# Ensure directory exists
os.makedirs(IMAGE_DIR, exist_ok=True)

# DATABASE SETUP
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp_sent INTEGER,
        timestamp_received INTEGER,
        latency_ms REAL,
        image_path TEXT
    )
    """)

    conn.commit()
    conn.close()


# PACKET PARSER
def parse_packet(payload: bytes):
    """
    Parse binary packet:
    [8 bytes timestamp][4 bytes size][image]
    """
    if len(payload) < 12:
        raise ValueError("Payload too small")

    # Little-endian unpack
    timestamp_sent = struct.unpack("<Q", payload[0:8])[0]
    image_size = struct.unpack("<I", payload[8:12])[0]

    image_data = payload[12:12 + image_size]

    if len(image_data) != image_size:
        raise ValueError("Image size mismatch")

    return timestamp_sent, image_data


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

    cursor.execute("""
    INSERT INTO images (timestamp_sent, timestamp_received, latency_ms, image_path)
    VALUES (?, ?, ?, ?)
    """, (timestamp_sent, timestamp_received, latency_ms, image_path))

    conn.commit()
    conn.close()


# MQTT CALLBACKS
def on_connect(client, userdata, flags, rc):
    print(f"[MQTT] Connected with result code {rc}")
    client.subscribe(MQTT_TOPIC)


def on_message(client, userdata, msg):
    try:
        recv_time_us = int(time.time() * 1_000_000)

        # Parse packet
        timestamp_sent, image_data = parse_packet(msg.payload)

        # Compute latency (ms)
        latency_ms = (recv_time_us - timestamp_sent) / 1000.0

        # Save image
        image_path = save_image(image_data, recv_time_us)

        # Store to DB
        store_metadata(timestamp_sent, recv_time_us, latency_ms, image_path)

        print(f"[RECV] Image saved: {image_path}")
        print(f"[INFO] Latency: {latency_ms:.2f} ms")

    except Exception as e:
        print(f"[ERROR] {e}")


# MAIN
def main():
    init_db()

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_BROKER, MQTT_PORT, 60)

    print("[SYSTEM] Subscriber started...")
    client.loop_forever()


if __name__ == "__main__":
    main()
