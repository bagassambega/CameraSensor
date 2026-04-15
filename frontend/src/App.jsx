import { useEffect, useState } from "react";

const WS_URL = "ws://localhost:8000/ws";
const API_BASE = "http://localhost:8000";
const MAX_LATENCY_POINTS = 24;

function App() {
  const [images, setImages] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const [latencyPoints, setLatencyPoints] = useState([]);

  useEffect(() => {
    const ws = new WebSocket(WS_URL);

    ws.onopen = () => setIsConnected(true);
    ws.onclose = () => setIsConnected(false);

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      setImages((prev) => [data, ...prev].slice(0, 100));
      setLatencyPoints((prev) =>
        [data.latency, ...prev].slice(0, MAX_LATENCY_POINTS),
      );
    };

    return () => ws.close();
  }, []);

  const latestStats = images[0]?.stats;
  const imageCount = images.length;
  const latestLatency = images[0]?.latency;
  const sparklineWidth = 320;
  const sparklineHeight = 96;

  return (
    <div className="min-h-screen bg-[#050816] text-slate-100">
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -left-24 top-0 h-72 w-72 rounded-full bg-cyan-500/20 blur-3xl animate-[pulse_8s_ease-in-out_infinite]" />
        <div className="absolute -right-32 top-24 h-96 w-96 rounded-full bg-fuchsia-500/15 blur-3xl animate-[pulse_10s_ease-in-out_infinite]" />
        <div className="absolute -bottom-24 left-1/3 h-80 w-80 rounded-full bg-emerald-500/15 blur-3xl animate-[pulse_12s_ease-in-out_infinite]" />
        <div className="absolute inset-0 bg-[linear-gradient(rgba(148,163,184,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,0.05)_1px,transparent_1px)] bg-size-[32px_32px] opacity-35" />
      </div>

      <div className="relative mx-auto flex min-h-screen w-full max-w-7xl flex-col px-4 py-6 sm:px-6 lg:px-8">
        <header className="overflow-hidden rounded-4xl border border-cyan-400/20 bg-white/5 shadow-[0_0_0_1px_rgba(34,211,238,0.08),0_20px_80px_rgba(0,0,0,0.45)] backdrop-blur-xl">
          <div className="border-b border-white/10 px-6 py-4 sm:px-8">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-cyan-400/15 ring-1 ring-cyan-300/20">
                  <span className="h-2.5 w-2.5 rounded-full bg-cyan-300 shadow-[0_0_18px_rgba(34,211,238,0.9)]" />
                </div>
                <div>
                  <h1 className="text-2xl font-semibold tracking-tight text-white sm:text-3xl">
                    Camera Detection Dashboard
                  </h1>
                </div>
              </div>

              <div className="inline-flex items-center gap-2 self-start rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-slate-200 sm:self-auto">
                <span
                  className={`h-2.5 w-2.5 rounded-full ${isConnected ? "bg-emerald-400 shadow-[0_0_16px_rgba(74,222,128,0.9)]" : "bg-rose-400 shadow-[0_0_16px_rgba(248,113,113,0.9)]"}`}
                />
                {isConnected ? "Websocket live" : "Awaiting websocket"}
              </div>
            </div>
          </div>

          <div className="grid gap-4 px-6 py-6 sm:px-8 lg:grid-cols-[1.25fr_0.75fr]">
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <StatPill label="Images" value={String(imageCount)} tone="cyan" />
              <StatPill
                label="Avg latency"
                value={
                  latestStats
                    ? `${latestStats.avg_latency.toFixed(2)} ms`
                    : "--"
                }
                tone="amber"
              />
              <StatPill
                label="Packet loss"
                value={latestStats ? String(latestStats.packet_loss) : "--"}
                tone="rose"
              />
              <StatPill
                label="Avg interval"
                value={
                  latestStats
                    ? `${latestStats.avg_interval.toFixed(2)} s`
                    : "--"
                }
                tone="emerald"
              />
            </div>

            <div className="rounded-[1.75rem] border border-white/10 bg-slate-950/60 p-4 ring-1 ring-cyan-400/10">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-400">
                    Latency trace
                  </p>
                  <p className="mt-1 text-sm text-slate-200">
                    Live sparkline for the last {MAX_LATENCY_POINTS} packets
                  </p>
                </div>
                <div className="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-xs text-cyan-200">
                  {latestLatency ? `${latestLatency.toFixed(2)} ms` : "No data"}
                </div>
              </div>

              <div className="mt-4 overflow-hidden rounded-2xl border border-white/10 bg-black/30 p-3">
                <Sparkline
                  values={latencyPoints}
                  width={sparklineWidth}
                  height={sparklineHeight}
                />
              </div>
            </div>
          </div>
        </header>

        <main className="mt-6 flex-1 space-y-6">
          {latestStats ? (
            <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <MetricCard
                title="Packets received"
                value={`${latestStats.total_received} / ${latestStats.expected}`}
                caption={`Packet loss: ${latestStats.packet_loss}`}
                accent="from-cyan-400 to-blue-500"
              />
              <MetricCard
                title="Latency range"
                value={`${latestStats.min_latency.toFixed(2)} - ${latestStats.max_latency.toFixed(2)} ms`}
                caption="Fastest and slowest observed packets"
                accent="from-fuchsia-400 to-pink-500"
              />
              <MetricCard
                title="Session average"
                value={`${latestStats.avg_latency.toFixed(2)} ms`}
                caption="Running average across the current session"
                accent="from-amber-400 to-orange-500"
              />
              <MetricCard
                title="Capture cadence"
                value={`${latestStats.avg_interval.toFixed(2)} s`}
                caption="Average time between received frames"
                accent="from-emerald-400 to-teal-500"
              />
            </section>
          ) : (
            <section className="rounded-[1.75rem] border border-dashed border-white/10 bg-white/5 p-8 text-center text-slate-300 shadow-[0_0_0_1px_rgba(255,255,255,0.03)] backdrop-blur-xl">
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl border border-cyan-400/20 bg-cyan-400/10 text-2xl">
                📡
              </div>
              <h2 className="mt-4 text-lg font-semibold text-white">
                Waiting for camera data
              </h2>
              <p className="mt-2 text-sm text-slate-400">
                Once MQTT packets arrive, live telemetry and image tiles will
                fill the console.
              </p>
            </section>
          )}

          <section className="rounded-[1.75rem] border border-white/10 bg-white/5 p-4 shadow-[0_0_0_1px_rgba(255,255,255,0.03)] backdrop-blur-xl sm:p-6">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold tracking-tight text-white">
                  Latest captures
                </h2>
                <p className="text-sm text-slate-400">
                  Recent image frames pushed from the device over MQTT.
                </p>
              </div>
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-medium text-slate-300">
                Showing up to 100 frames
              </span>
            </div>

            {images.length > 0 ? (
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
                {images.map((img, i) => (
                  <article
                    key={`${img.timestamp ?? i}-${i}`}
                    className="group overflow-hidden rounded-3xl border border-white/10 bg-slate-950/70 shadow-lg shadow-black/20 transition duration-300 hover:-translate-y-1 hover:border-cyan-400/30 hover:shadow-cyan-500/10"
                  >
                    <div className="relative aspect-4/3 overflow-hidden bg-slate-900">
                      <img
                        src={`${API_BASE}${img.image_url}`}
                        alt={`Captured frame ${i + 1}`}
                        className="h-full w-full object-cover transition duration-500 group-hover:scale-105"
                        loading="lazy"
                      />
                      <div className="absolute left-3 top-3 rounded-full border border-white/15 bg-slate-950/70 px-2.5 py-1 text-xs font-medium text-cyan-200 backdrop-blur">
                        {img.latency.toFixed(2)} ms
                      </div>
                    </div>
                    <div className="flex items-center justify-between gap-3 px-4 py-3">
                      <div>
                        <p className="text-sm font-medium text-white">
                          Live frame
                        </p>
                        <p className="text-xs text-slate-400">
                          {new Date(img.timestamp / 1000).toLocaleTimeString()}
                        </p>
                      </div>
                      <span className="rounded-full border border-emerald-400/20 bg-emerald-400/10 px-2.5 py-1 text-xs font-semibold text-emerald-300">
                        Online
                      </span>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <div className="rounded-2xl border border-dashed border-white/10 bg-black/20 p-8 text-center text-sm text-slate-400">
                No images received yet.
              </div>
            )}
          </section>
        </main>
      </div>
    </div>
  );
}

function StatPill({ label, value, tone }) {
  const tones = {
    cyan: "bg-cyan-400/10 text-cyan-100 ring-cyan-400/20",
    amber: "bg-amber-400/10 text-amber-100 ring-amber-400/20",
    rose: "bg-rose-400/10 text-rose-100 ring-rose-400/20",
    emerald: "bg-emerald-400/10 text-emerald-100 ring-emerald-400/20",
  };

  return (
    <div
      className={`rounded-3xl border p-4 shadow-lg shadow-black/10 ${tones[tone]}`}
    >
      <p className="text-xs font-medium uppercase tracking-[0.22em] opacity-80">
        {label}
      </p>
      <p className="mt-2 text-lg font-semibold text-white">{value}</p>
    </div>
  );
}

function MetricCard({ title, value, caption, accent }) {
  return (
    <article className="overflow-hidden rounded-[1.75rem] border border-white/10 bg-white/5 p-5 shadow-[0_0_0_1px_rgba(255,255,255,0.03)] backdrop-blur-xl">
      <div className={`mb-4 h-1.5 rounded-full bg-linear-to-r ${accent}`} />
      <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">
        {title}
      </p>
      <p className="mt-2 text-2xl font-semibold tracking-tight text-white">
        {value}
      </p>
      <p className="mt-2 text-sm leading-6 text-slate-400">{caption}</p>
    </article>
  );
}

function Sparkline({ values, width, height }) {
  const points = values.length > 0 ? values : [0];
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;

  const path = points
    .map((value, index) => {
      const x = (index / Math.max(points.length - 1, 1)) * width;
      const y = height - ((value - min) / range) * (height - 12) - 6;
      return `${index === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="h-24 w-full overflow-visible"
    >
      <defs>
        <linearGradient id="sparklineStroke" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#22d3ee" />
          <stop offset="50%" stopColor="#a78bfa" />
          <stop offset="100%" stopColor="#34d399" />
        </linearGradient>
        <linearGradient id="sparklineFill" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="rgba(34, 211, 238, 0.28)" />
          <stop offset="100%" stopColor="rgba(34, 211, 238, 0)" />
        </linearGradient>
      </defs>

      <path
        d={`${path} L ${width} ${height} L 0 ${height} Z`}
        fill="url(#sparklineFill)"
      />
      <path
        d={path}
        fill="none"
        stroke="url(#sparklineStroke)"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {points.length > 1 && (
        <circle
          cx={(width / Math.max(points.length - 1, 1)) * (points.length - 1)}
          cy={
            height -
            ((points[points.length - 1] - min) / range) * (height - 12) -
            6
          }
          r="4"
          fill="#22d3ee"
          className="drop-shadow-[0_0_10px_rgba(34,211,238,0.9)]"
        />
      )}
    </svg>
  );
}

export default App;
