CREATE TABLE images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_group INTEGER,
    timestamp_sent INTEGER,
    timestamp_received INTEGER,
    latency_ms REAL,
    image_path TEXT
);