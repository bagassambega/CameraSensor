from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import sqlite3

app = FastAPI()

DB_NAME = "camerasensor.db"
IMAGE_DIR = "received"

# Serve images as static files
app.mount("/images", StaticFiles(directory=IMAGE_DIR), name="images")


# DB HELPER
def query_db(query):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    return rows


# GET ALL IMAGES
@app.get("/api/images")
def get_images():
    rows = query_db("""
        SELECT id, timestamp_sent, timestamp_received, latency_ms, image_path
        FROM images
        ORDER BY timestamp_received DESC
        LIMIT 100
    """)

    result = []
    for r in rows:
        result.append({
            "id": r[0],
            "timestamp_sent": r[1],
            "timestamp_received": r[2],
            "latency_ms": r[3],
            "image_url": f"/images/{r[4].split('/')[-1]}"
        })

    return result


# METRICS
@app.get("/api/metrics")
def get_metrics():
    rows = query_db("""
        SELECT latency_ms, timestamp_received
        FROM images
        ORDER BY timestamp_received ASC
    """)

    if not rows:
        return {}

    latencies = [r[0] for r in rows]
    timestamps = [r[1] for r in rows]

    # latency
    avg_latency = sum(latencies) / len(latencies)
    min_latency = min(latencies)
    max_latency = max(latencies)

    # interval
    intervals = []
    for i in range(1, len(timestamps)):
        dt = (timestamps[i] - timestamps[i-1]) / 1_000_000
        intervals.append(dt)

    avg_interval = sum(intervals) / len(intervals) if intervals else 0

    return {
        "total_received": len(rows),
        "avg_latency": avg_latency,
        "min_latency": min_latency,
        "max_latency": max_latency,
        "avg_interval": avg_interval
    }