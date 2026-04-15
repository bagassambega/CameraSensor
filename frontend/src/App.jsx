import { useEffect, useState } from "react";

const WS_URL = "ws://localhost:8000/ws";
const API_BASE = "http://localhost:8000";

function App() {
  const [images, setImages] = useState([]);

  useEffect(() => {
    const ws = new WebSocket(WS_URL);

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      setImages((prev) => [data, ...prev].slice(0, 100));
    };

    return () => ws.close();
  }, []);

  const latestStats = images[0]?.stats;

  return (
    <div
      style={{
        padding: "20px",
        backgroundColor: "#f5f5f5",
        minHeight: "100vh",
        fontFamily: "system-ui, -apple-system, sans-serif",
      }}
    >
      <h1 style={{ color: "#333" }}>Live IoT Dashboard</h1>

      {latestStats && (
        <div
          style={{
            backgroundColor: "white",
            borderRadius: "8px",
            padding: "20px",
            marginBottom: "20px",
            boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
            gap: "20px",
          }}
        >
          <div>
            <p style={{ color: "#999", fontSize: "12px", margin: "0 0 5px 0" }}>
              PACKETS RECEIVED
            </p>
            <p
              style={{
                color: "#333",
                fontSize: "24px",
                fontWeight: "bold",
                margin: 0,
              }}
            >
              {latestStats.total_received} / {latestStats.expected}
            </p>
            <p
              style={{
                color: "#e74c3c",
                fontSize: "12px",
                margin: "5px 0 0 0",
              }}
            >
              Loss: {latestStats.packet_loss}
            </p>
          </div>

          <div>
            <p style={{ color: "#999", fontSize: "12px", margin: "0 0 5px 0" }}>
              AVERAGE LATENCY
            </p>
            <p
              style={{
                color: "#333",
                fontSize: "24px",
                fontWeight: "bold",
                margin: 0,
              }}
            >
              {latestStats.avg_latency.toFixed(2)} ms
            </p>
          </div>

          <div>
            <p style={{ color: "#999", fontSize: "12px", margin: "0 0 5px 0" }}>
              MIN / MAX LATENCY
            </p>
            <p
              style={{
                color: "#333",
                fontSize: "24px",
                fontWeight: "bold",
                margin: 0,
              }}
            >
              {latestStats.min_latency.toFixed(2)} /{" "}
              {latestStats.max_latency.toFixed(2)} ms
            </p>
          </div>

          <div>
            <p style={{ color: "#999", fontSize: "12px", margin: "0 0 5px 0" }}>
              AVG INTERVAL
            </p>
            <p
              style={{
                color: "#333",
                fontSize: "24px",
                fontWeight: "bold",
                margin: 0,
              }}
            >
              {latestStats.avg_interval.toFixed(2)} s
            </p>
          </div>
        </div>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
          gap: "10px",
        }}
      >
        {images.map((img, i) => (
          <div
            key={i}
            style={{
              backgroundColor: "white",
              borderRadius: "8px",
              padding: "10px",
              boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
              overflow: "hidden",
            }}
          >
            <img
              src={`${API_BASE}${img.image_url}`}
              style={{ width: "100%", borderRadius: "4px" }}
            />
            <p style={{ color: "#666", marginTop: "8px", marginBottom: 0 }}>
              {img.latency.toFixed(2)} ms
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

export default App;
