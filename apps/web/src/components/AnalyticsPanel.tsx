interface Indicators {
  latest: {
    ema20?: number | null;
    ema50?: number | null;
    ema200?: number | null;
    rsi14?: number | null;
    macd?: { line?: number | null; signal?: number | null; hist?: number | null };
    stoch?: { k?: number | null; d?: number | null };
    adx14?: number | null;
    plus_di?: number | null;
    minus_di?: number | null;
    atr14?: number | null;
    bollinger?: { upper?: number | null; mid?: number | null; lower?: number | null };
    historical_volatility?: number | null;
    volatility_percentile?: number | null;
    roc9?: number | null;
  };
  divergences: { rsi: { kind: string; detail: string }[]; macd_hist: { kind: string; detail: string }[] };
}

interface Structure {
  trend: string;
  supports: { price: number; touches: number }[];
  resistances: { price: number; touches: number }[];
  prev_day: { high: number | null; low: number | null };
  prev_week: { high: number | null; low: number | null };
  events: { kind: string; level: number; detail: string }[];
  mtf_trend: { interval: string; trend: string; strength: string | null; adx: number | null }[];
}

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

const fmt = (v: number | null | undefined, d = 2) =>
  v == null ? "—" : v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });

const EVENT_LABELS: Record<string, string> = {
  bos_bullish: "BOS ↑",
  bos_bearish: "BOS ↓",
  choch_bullish: "CHoCH ↑",
  choch_bearish: "CHoCH ↓",
};

async function AnalyticsData() {
  const [ind, struct] = await Promise.all([
    fetch(`${API_INTERNAL_URL}/api/v1/markets/XAUUSD/indicators?interval=1day`, {
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    })
      .then((r) => (r.ok ? (r.json() as Promise<Indicators>) : null))
      .catch(() => null),
    fetch(`${API_INTERNAL_URL}/api/v1/markets/XAUUSD/structure?interval=1h`, {
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    })
      .then((r) => (r.ok ? (r.json() as Promise<Structure>) : null))
      .catch(() => null),
  ]);

  if (!ind || !struct) {
    return (
      <p className="rounded-lg border border-red-900 bg-red-950/40 p-4 text-xs text-red-300">
        Analytics engine unreachable (indicators/structure endpoints failed).
      </p>
    );
  }

  const l = ind.latest;
  const trendColor =
    struct.trend === "up" ? "text-emerald-400" : struct.trend === "down" ? "text-red-400" : "text-amber-400";

  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
      {/* Momentum & trend */}
      <div className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-4">
        <h3 className="text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
          Daily momentum & trend
        </h3>
        <dl className="mt-3 space-y-1.5 font-mono text-xs">
          {[
            ["RSI(14)", fmt(l.rsi14, 1)],
            ["MACD hist", fmt(l.macd?.hist)],
            ["Stoch %K/%D", `${fmt(l.stoch?.k, 0)}/${fmt(l.stoch?.d, 0)}`],
            ["ADX(14)", `${fmt(l.adx14, 1)} (+DI ${fmt(l.plus_di, 0)} / -DI ${fmt(l.minus_di, 0)})`],
            ["ROC(9)", `${fmt(l.roc9)}%`],
            ["ATR(14)", fmt(l.atr14)],
          ].map(([k, v]) => (
            <div key={k} className="flex justify-between gap-2">
              <dt className="text-neutral-500">{k}</dt>
              <dd className="text-neutral-300">{v}</dd>
            </div>
          ))}
        </dl>
        <div className="mt-3 border-t border-neutral-800 pt-2 font-mono text-[10px] text-neutral-500">
          Volatility: HV {fmt(l.historical_volatility, 1)}% · percentile{" "}
          {fmt(l.volatility_percentile, 0)}
        </div>
        {(ind.divergences.rsi.length > 0 || ind.divergences.macd_hist.length > 0) && (
          <div className="mt-2 font-mono text-[10px] text-amber-400">
            Divergence: {ind.divergences.rsi.at(-1)?.kind ?? ind.divergences.macd_hist.at(-1)?.kind}(
            {ind.divergences.rsi.length + ind.divergences.macd_hist.length} recent)
          </div>
        )}
      </div>

      {/* Market structure */}
      <div className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-4">
        <h3 className="text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
          Market structure (1H)
        </h3>
        <div className={`mt-2 font-mono text-lg font-semibold ${trendColor}`}>
          {struct.trend.toUpperCase()}
        </div>
        <dl className="mt-2 space-y-1 font-mono text-xs">
          <div className="flex justify-between gap-2">
            <dt className="text-neutral-500">Prev day H/L</dt>
            <dd className="text-neutral-300">
              {fmt(struct.prev_day.high, 1)} / {fmt(struct.prev_day.low, 1)}
            </dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt className="text-neutral-500">Prev week H/L</dt>
            <dd className="text-neutral-300">
              {fmt(struct.prev_week.high, 1)} / {fmt(struct.prev_week.low, 1)}
            </dd>
          </div>
        </dl>
        <div className="mt-3 font-mono text-[10px] leading-relaxed text-neutral-500">
          <span className="text-emerald-400">
            S: {struct.supports.map((s) => fmt(s.price, 1)).join(" · ") || "—"}
          </span>
          <br />
          <span className="text-red-400">
            R: {struct.resistances.map((r) => fmt(r.price, 1)).join(" · ") || "—"}
          </span>
        </div>
        <div className="mt-3 space-y-1 font-mono text-[10px] text-neutral-400">
          {struct.events.slice(-3).reverse().map((e, i) => (
            <div key={i}>
              <span className="text-neutral-200">{EVENT_LABELS[e.kind] ?? e.kind}</span> @ {fmt(e.level, 1)}
            </div>
          ))}
        </div>
      </div>

      {/* Multi-timeframe */}
      <div className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-4">
        <h3 className="text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
          Multi-timeframe trend
        </h3>
        <div className="mt-3 space-y-2">
          {struct.mtf_trend.map((m) => {
            const c =
              m.trend === "up" ? "text-emerald-400" : m.trend === "down" ? "text-red-400" : "text-amber-400";
            return (
              <div key={m.interval} className="flex items-center justify-between font-mono text-xs">
                <span className="text-neutral-500">{m.interval}</span>
                <span className={c}>
                  {m.trend}
                  {m.strength ? ` · ${m.strength}` : ""}
                  {m.adx != null ? ` (ADX ${m.adx})` : ""}
                </span>
              </div>
            );
          })}
        </div>
        <p className="mt-3 border-t border-neutral-800 pt-2 text-[10px] leading-relaxed text-neutral-600">
          EMA alignment + ADX per timeframe. Deterministic computation from stored candles — no
          look-ahead; swing levels require their confirmation bars.
        </p>
      </div>
    </div>
  );
}

export function AnalyticsSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
      {[0, 1, 2].map((i) => (
        <div key={i} className="h-48 animate-pulse rounded-lg border border-neutral-800 bg-neutral-900/40" />
      ))}
    </div>
  );
}

export { AnalyticsData };
