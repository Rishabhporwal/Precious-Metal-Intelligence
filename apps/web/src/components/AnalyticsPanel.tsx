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
      <p className="card p-5 border-[rgba(246,70,93,0.3)] bg-[var(--down-dim)] text-xs text-down">
        Analytics engine unreachable (indicators/structure endpoints failed).
      </p>
    );
  }

  const l = ind.latest;
  const trendColor =
    struct.trend === "up" ? "text-up" : struct.trend === "down" ? "text-down" : "text-warn";

  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
      {/* Momentum & trend */}
      <div className="card p-5">
        <h3 className="card-title text-muted">
          Daily momentum & trend
        </h3>
        <dl className="mt-3 space-y-1.5 num text-xs">
          {[
            ["RSI(14)", fmt(l.rsi14, 1)],
            ["MACD hist", fmt(l.macd?.hist)],
            ["Stoch %K/%D", `${fmt(l.stoch?.k, 0)}/${fmt(l.stoch?.d, 0)}`],
            ["ADX(14)", `${fmt(l.adx14, 1)} (+DI ${fmt(l.plus_di, 0)} / -DI ${fmt(l.minus_di, 0)})`],
            ["ROC(9)", `${fmt(l.roc9)}%`],
            ["ATR(14)", fmt(l.atr14)],
          ].map(([k, v]) => (
            <div key={k} className="flex justify-between gap-2">
              <dt className="text-muted">{k}</dt>
              <dd className="text-ink-soft">{v}</dd>
            </div>
          ))}
        </dl>
        <div className="mt-3 border-t border-line pt-2 num text-[10px] text-muted">
          Volatility: HV {fmt(l.historical_volatility, 1)}% · percentile{" "}
          {fmt(l.volatility_percentile, 0)}
        </div>
        {(ind.divergences.rsi.length > 0 || ind.divergences.macd_hist.length > 0) && (
          <div className="mt-2 num text-[10px] text-warn">
            Divergence: {ind.divergences.rsi.at(-1)?.kind ?? ind.divergences.macd_hist.at(-1)?.kind}(
            {ind.divergences.rsi.length + ind.divergences.macd_hist.length} recent)
          </div>
        )}
      </div>

      {/* Market structure */}
      <div className="card p-5">
        <h3 className="card-title text-muted">
          Market structure (1H)
        </h3>
        <div className={`mt-2 num text-lg font-semibold ${trendColor}`}>
          {struct.trend.toUpperCase()}
        </div>
        <dl className="mt-2 space-y-1 num text-xs">
          <div className="flex justify-between gap-2">
            <dt className="text-muted">Prev day H/L</dt>
            <dd className="text-ink-soft">
              {fmt(struct.prev_day.high, 1)} / {fmt(struct.prev_day.low, 1)}
            </dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt className="text-muted">Prev week H/L</dt>
            <dd className="text-ink-soft">
              {fmt(struct.prev_week.high, 1)} / {fmt(struct.prev_week.low, 1)}
            </dd>
          </div>
        </dl>
        <div className="mt-3 num text-[10px] leading-relaxed text-muted">
          <span className="text-up">
            S: {struct.supports.map((s) => fmt(s.price, 1)).join(" · ") || "—"}
          </span>
          <br />
          <span className="text-down">
            R: {struct.resistances.map((r) => fmt(r.price, 1)).join(" · ") || "—"}
          </span>
        </div>
        <div className="mt-3 space-y-1 num text-[10px] text-muted">
          {struct.events.slice(-3).reverse().map((e, i) => (
            <div key={i}>
              <span className="text-ink-soft">{EVENT_LABELS[e.kind] ?? e.kind}</span> @ {fmt(e.level, 1)}
            </div>
          ))}
        </div>
      </div>

      {/* Multi-timeframe */}
      <div className="card p-5">
        <h3 className="card-title text-muted">
          Multi-timeframe trend
        </h3>
        <div className="mt-3 space-y-2">
          {struct.mtf_trend.map((m) => {
            const c =
              m.trend === "up" ? "text-up" : m.trend === "down" ? "text-down" : "text-warn";
            return (
              <div key={m.interval} className="flex items-center justify-between num text-xs">
                <span className="text-muted">{m.interval}</span>
                <span className={c}>
                  {m.trend}
                  {m.strength ? ` · ${m.strength}` : ""}
                  {m.adx != null ? ` (ADX ${m.adx})` : ""}
                </span>
              </div>
            );
          })}
        </div>
        <p className="mt-3 border-t border-line pt-2 text-[10px] leading-relaxed text-faint">
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
        <div key={i} className="h-48 animate-pulse card animate-pulse opacity-60" />
      ))}
    </div>
  );
}

export { AnalyticsData };
