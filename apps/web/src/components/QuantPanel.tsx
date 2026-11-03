interface QuantResponse {
  regime: { regime: string; trend: { trend: string }; vol: { vol_regime: string; hv: number | null; percentile: number | null }; strength: { adx: number | null; strength: string } };
  correlations: { series_id: string; rolling_30d: number | null; full_sample: number | null; last_macro_date: string | null }[];
  gold_silver: { full_sample: number | null; data_quality_caveat: string | null } | null;
  scenarios: {
    current_bucket: string;
    bucket_history: Record<string, { n: number; median_pct: number; mean_pct: number; up_rate: number }>;
    baseline: Record<string, { n: number; median_pct: number; mean_pct: number; up_rate: number }>;
    history_years: number;
    note: string;
  };
}

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

const CORR_LABELS: Record<string, string> = {
  DGS10: "10Y yield",
  DFII10: "10Y real yield",
  DTWEXBGS: "Broad USD",
  DCOILWTICO: "WTI",
};

function fmtPct(v: number | null | undefined): string {
  return v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

export async function QuantData() {
  const q = await fetch(`${API_INTERNAL_URL}/api/v1/markets/XAUUSD/quant`, {
    cache: "no-store",
    signal: AbortSignal.timeout(30000),
  })
    .then((r) => (r.ok ? (r.json() as Promise<QuantResponse>) : null))
    .catch(() => null);

  if (!q) {
    return (
      <p className="card p-5 border-[rgba(246,70,93,0.3)] bg-[var(--down-dim)] text-xs text-down">
        Quant engine unreachable.
      </p>
    );
  }

  const corrColor = (v: number | null) =>
    v == null ? "text-muted" : v > 0.2 ? "text-up" : v < -0.2 ? "text-down" : "text-ink-soft";

  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
      <div className="card p-5">
        <h3 className="card-title text-muted">Regime (daily)</h3>
        <div className="mt-2 num text-sm font-semibold text-ink">{q.regime.regime}</div>
        <dl className="mt-3 space-y-1 num text-[11px]">
          <div className="flex justify-between">
            <dt className="text-muted">HV(20) / percentile</dt>
            <dd className="text-ink-soft">
              {q.regime.vol.hv ?? "—"}% / {q.regime.vol.percentile ?? "—"}
            </dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted">ADX(14)</dt>
            <dd className="text-ink-soft">{q.regime.strength.adx ?? "—"} ({q.regime.strength.strength})</dd>
          </div>
        </dl>
        <h3 className="mt-4 card-title text-muted">
          Rolling 30d correlations (daily returns)
        </h3>
        <dl className="mt-2 space-y-1 num text-[11px]">
          {q.correlations.map((c) => (
            <div key={c.series_id} className="flex justify-between">
              <dt className="text-muted">{CORR_LABELS[c.series_id] ?? c.series_id}</dt>
              <dd className={corrColor(c.rolling_30d)}>
                {c.rolling_30d?.toFixed(2) ?? "—"} <span className="text-faint">(all {c.full_sample?.toFixed(2) ?? "—"})</span>
              </dd>
            </div>
          ))}
        </dl>
        {q.gold_silver && (
          <p className="mt-2 num text-[10px] text-faint">
            gold/silver {q.gold_silver.full_sample?.toFixed(2) ?? "—"}
            {q.gold_silver.data_quality_caveat ? ` ⚠ ${q.gold_silver.data_quality_caveat}` : ""}
          </p>
        )}
      </div>

      <div className="md:col-span-2 card p-5">
        <h3 className="card-title text-muted">
          Historical scenario — bucket: {q.scenarios.current_bucket} (past {q.scenarios.history_years}y)
        </h3>
        <table className="mt-3 w-full text-left num text-[11px]">
          <thead className="text-faint">
            <tr>
              <th className="py-1">Horizon</th>
              <th>n</th>
              <th>Median</th>
              <th>Mean</th>
              <th>Up rate</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(q.scenarios.bucket_history).map(([h, s]) => {
              const base = q.scenarios.baseline?.[h];
              return (
                <tr key={h} className="border-t border-line">
                  <td className="py-1 text-ink-soft">{h}</td>
                  <td className="text-muted">{s.n}</td>
                  <td className="text-ink-soft">{fmtPct(s.median_pct)}</td>
                  <td className="text-muted">{fmtPct(s.mean_pct)}</td>
                  <td className={s.up_rate >= 0.5 ? "text-up" : "text-down"}>
                    {(s.up_rate * 100).toFixed(1)}%
                    {base && <span className="text-faint"> (all: {(base.up_rate * 100).toFixed(1)}%)</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className="mt-3 text-[10px] leading-relaxed text-faint">{q.scenarios.note}</p>
      </div>
    </div>
  );
}

export function QuantSkeleton() {
  return <div className="h-48 animate-pulse card animate-pulse opacity-60" />;
}

export function QuantPanel() {
  return (
    <section>
      <h2 className="mb-2 card-title text-muted">
        Quant engine
      </h2>
      <QuantData />
    </section>
  );
}
