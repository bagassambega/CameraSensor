import { useEffect, useState } from "react";

const API_BASE = "http://localhost:8000";

function App() {
  const [images, setImages] = useState([]);
  const [metrics, setMetrics] = useState({});

  // Fetch images
  const fetchImages = async () => {
    const res = await fetch(`${API_BASE}/api/images`);
    const data = await res.json();
    setImages(data);
  };

  // Fetch metrics
  const fetchMetrics = async () => {
    const res = await fetch(`${API_BASE}/api/metrics`);
    const data = await res.json();
    setMetrics(data);
  };

  useEffect(() => {
    const initialLoad = setTimeout(() => {
      void fetchImages();
      void fetchMetrics();
    }, 0);

    const interval = setInterval(() => {
      void fetchImages();
      void fetchMetrics();
    }, 2000);

    return () => {
      clearTimeout(initialLoad);
      clearInterval(interval);
    };
  }, []);

  return (
    <div style={{ padding: "20px", fontFamily: "Arial" }}>
      <h1>IoT Image Monitoring Dashboard</h1>

      {/* ===== METRICS ===== */}
      <div
        style={{
          display: "flex",
          gap: "20px",
          marginBottom: "20px",
        }}
      >
        <Metric title="Total Received" value={metrics.total_received} />
        <Metric
          title="Avg Latency (ms)"
          value={metrics.avg_latency?.toFixed(2)}
        />
        <Metric
          title="Min Latency (ms)"
          value={metrics.min_latency?.toFixed(2)}
        />
        <Metric
          title="Max Latency (ms)"
          value={metrics.max_latency?.toFixed(2)}
        />
        <Metric
          title="Avg Interval (s)"
          value={metrics.avg_interval?.toFixed(2)}
        />
      </div>

      {/* ===== IMAGE GRID ===== */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
          gap: "15px",
        }}
      >
        {images.map((img) => (
          <div
            key={img.id}
            style={{
              border: "1px solid #ccc",
              padding: "10px",
            }}
          >
            <img
              src={`${API_BASE}${img.image_url}`}
              style={{ width: "100%" }}
            />
            <p style={{ fontSize: "12px" }}>
              Latency: {img.latency_ms.toFixed(2)} ms
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

function Metric({ title, value }) {
  return (
    <div
      style={{
        border: "1px solid #ccc",
        padding: "10px",
        minWidth: "150px",
      }}
    >
      <h4>{title}</h4>
      <p>{value ?? "-"}</p>
    </div>
  );
}

export default App;
