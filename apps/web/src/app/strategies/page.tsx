import { Suspense } from "react";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

interface StrategyInfo {
  strategy_id: string;
  name: string;
  description: string;
  default_params: Record<string, unknown>;
  enabled: boolean;
  algo_version: string;
}

interface Detection {
  strategy_id: string;
  interval: string;
  direction: string;
  status: string;
  anchor_time: string;
  levels: Record<string, number>;
  evidence: string[];
}

interface Candle {
  market_ts: string;
  open: string;
  high: string;
  low: string;
  close: string;
}

async function StrategiesData() {
  const [reg, dets, candles] = await Promise.all([
    fetch(`${API_INTERNAL_URL}/api/v1/strategies`, { cache: "no-store", signal: AbortSignal.timeout(15000) })
      .then((r) => (r.ok ? (r.json() as Promise<{ strategies: StrategyInfo[] }>) : null))
      .catch(() => null),
    fetch(`${API_INTERNAL_URL}/api/v1/strategies/detections?symbol=XAUUSD&limit=40`, {
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    })
      .then((r) => (r.ok ? (r.json() as Promise<{ detections: Detection[]; count: number }>) : null))
      .catch(() => null),
    fetch(`${API_INTERNAL_URL}/api/v1/markets/XAUUSD/candles?interval=1h&limit=60`, {
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    })
      .then((r) => (r.ok ? (r.json() as Promise<{ candles: Candle[] }>) : null))
      .catch(() => null),
  ]);

  if (!reg || !dets) {
    return (
      <p className="card p-5 border-[rgba(246,70,93,0.3)] bg-[var(--down-dim)] text-sm text-down">
        Strategies API unreachable — check the api and quant services.
      </p>
    );
  }

  const active = dets.detections.filter((d) => d.status === "active").slice(0, 8);
  const lastCandle = candles?.candles.at(-1);
  const lastClose = lastCandle?.close ? Number(lastCandle.close) : null;
  const lo = candles ? Math.min(...candles.candles.map((c) => Number(c.low))) : 0;
  const hi = candles ? Math.max(...candles.candles.map((c) => Number(c.high))) : 1;
  const pctY = (price: number) =>
    Math.min(98, Math.max(2, 100 * (1 - (price - lo) / Math.max(1e-9, hi - lo))));

  return (
    <>
      {/* Detection chart annotations: active levels on the recent 1h range */}
      <section className="card p-5">
        <h2 className="card-title text-muted">
          Active levels — last 60×1H candles (annotation preview)
        </h2>
        <div className="relative mt-3 h-56">
          <svg viewBox="0 0 800 224" preserveAspectRatio="none" className="h-full w-full">
            {candles && (
              <polyline
                points={candles.candles
                  .map((c, i) => `${(i / (candles.candles.length - 1)) * 800},${pctY(Number(c.close)) * 2.24}`)
                  .join(" ")}
                fill="none"
                stroke="#f5c451"
                strokeWidth="1"
              />
            )}
          </svg>
          {active.map((d, i) => {
            const level = d.levels["level"] ?? d.levels["zone_high"] ?? d.levels["pool"] ?? d.levels["gap_high"];
            if (level == null || level < lo || level > hi) return null;
            const color = d.direction === "bullish" ? "#34d399" : d.direction === "bearish" ? "#f87171" : "#94a3b8";
            return (
              <div
                key={`${d.strategy_id}-${d.anchor_time}-${i}`}
                className="absolute left-0 flex w-full items-center justify-between border-t border-dashed px-2 text-[10px]"
                style={{ top: `${pctY(level)}%`, borderColor: color, color }}
              >
                <span>
                  {d.strategy_id} · {d.direction}
                </span>
                <span>{level.toFixed(2)}</span>
              </div>
            );
          })}
        </div>
        <p className="mt-2 text-[10px] text-faint">
          Active detections only (levels outside the visible range are omitted). Full TradingView
          zone boxes arrive with Phase 4 chart polish.
        </p>
      </section>

      {/* Registry */}
      <section className="mt-6">
        <h2 className="mb-2 card-title text-muted">
          Strategy registry ({reg.strategies.filter((s) => s.enabled).length}/{reg.strategies.length} enabled)
        </h2>
        <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
          {reg.strategies.map((s) => (
            <div key={s.strategy_id} className="rounded border border-line bg-white/[0.02] p-3">
              <div className="flex items-center justify-between">
                <span className="num text-xs text-ink-soft">{s.name}</span>
                <span
                  className={`rounded px-1.5 py-0.5 text-[10px] ${
                    s.enabled ? "bg-up/10 text-up" : "bg-white/[0.06] text-muted"
                  }`}
                >
                  {s.enabled ? "ENABLED" : "OFF"}
                </span>
              </div>
              <p className="mt-1 text-[10px] leading-relaxed text-muted">{s.description}</p>
              <p className="mt-1 num text-[10px] text-faint">
                {s.strategy_id} · {s.algo_version}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Detections table */}
      <section className="mt-6">
        <h2 className="mb-2 card-title text-muted">
          Recent detections (latest {dets.count})
        </h2>
        <div className="overflow-x-auto card">
          <table className="w-full text-left text-xs">
            <thead className="bg-white/[0.02] text-muted">
              <tr>
                {["Strategy", "Dir", "TF", "Status", "Anchor", "Levels", "Evidence"].map((h) => (
                  <th key={h} className="px-3 py-2 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {dets.detections.map((d, i) => (
                <tr key={i} className="border-t border-line align-top">
                  <td className="px-3 py-2 num text-[10px] text-ink-soft">{d.strategy_id}</td>
                  <td
                    className={`px-3 py-2 text-[10px] ${
                      d.direction === "bullish"
                        ? "text-up"
                        : d.direction === "bearish"
                          ? "text-down"
                          : "text-muted"
                    }`}
                  >
                    {d.direction}
                  </td>
                  <td className="px-3 py-2 text-[10px] text-muted">{d.interval}</td>
                  <td className="px-3 py-2 text-[10px]">
                    <span
                      className={
                        d.status === "active"
                          ? "text-up"
                          : d.status === "consumed"
                            ? "text-muted"
                            : "text-warn"
                      }
                    >
                      {d.status}
                    </span>
                  </td>
                  <td className="px-3 py-2 num text-[10px] text-muted">
                    {d.anchor_time.slice(5, 16).replace("T", " ")}
                  </td>
                  <td className="px-3 py-2 num text-[10px] text-muted">
                    {Object.entries(d.levels)
                      .filter(([k]) => !["atr", "body"].includes(k))
                      .slice(0, 3)
                      .map(([k, v]) => `${k} ${v != null ? Number(v).toFixed(2) : "—"}`)
                      .join(", ") || "—"}
                  </td>
                  <td className="max-w-[320px] px-3 py-2 text-[10px] leading-snug text-muted">
                    {d.evidence[0]}
                    {d.evidence.length > 1 ? ` (+${d.evidence.length - 1})` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {lastClose != null && (
          <p className="mt-2 text-[10px] text-faint">
            Current gold close: {lastClose.toFixed(2)} · detections are analysis records, NOT trade
            recommendations (risk validation lands in Phase 8).
          </p>
        )}
      </section>
    </>
  );
}

function StrategiesSkeleton() {
  return <div className="h-96 animate-pulse card animate-pulse opacity-60" />;
}

export default function StrategiesPage() {
  return (
    <main className="page rise">
      <div className="mx-auto max-w-5xl">
        <header className="mb-6">
          <h1 className="page-title">Advanced Strategies</h1>
          <p className="mt-1 text-xs text-muted">
            Phase 4 — SMC/ICT P0 detections on XAU/USD · deterministic, repaint-free, algo-versioned
          </p>
        </header>
        <Suspense fallback={<StrategiesSkeleton />}>
          <StrategiesData />
        </Suspense>
        <footer className="mt-8 border-t border-line-subtle pt-4 text-[10.5px] text-faint">
          <a className="text-muted underline" href="/">← dashboard</a> ·
          detections persist append-only in Postgres with algo version + params for reproducibility
        </footer>
      </div>
    </main>
  );
}
