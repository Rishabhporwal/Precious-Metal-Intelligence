import { STATUS_LABEL, fmtUsd } from "./predictionAuditShared";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

interface Prediction {
  id: number;
  direction: string;
  mode: string;
  entry: (number | null)[];
  stop: number | null;
  t1: number | null;
  t2: number | null;
  status: string;
  created_at: string | null;
  max_favorable: number | null;
  reason: string | null;
}

interface Summary {
  total: number;
  pending: number;
  decided: number;
  hit_t1: number;
  hit_t2: number;
  stopped: number;
  superseded?: number;
  expired: number;
  t1_hit_rate: number | null;
}

async function getJson<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_INTERNAL_URL}${path}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export default async function PredictionAuditView() {
  const [audit, summary] = await Promise.all([
    getJson<{ predictions?: Prediction[] }>("/api/v1/predictions/audit?symbol=XAUUSD&limit=50"),
    getJson<Summary>("/api/v1/predictions/summary?symbol=XAUUSD"),
  ]);
  const rows = audit?.predictions ?? [];
  const stats = summary
    ? [
        ["Predictions made", summary.total],
        ["Still in progress", summary.pending],
        ["Reached T1", summary.hit_t1 + summary.hit_t2],
        ["Reached T2", summary.hit_t2],
        ["Stopped out", summary.stopped],
        ["Superseded", summary.superseded ?? 0],
        ["T1 accuracy", summary.t1_hit_rate == null ? "—" : `${Math.round(summary.t1_hit_rate * 100)}%`],
      ]
    : [];

  return (
    <div>
      <h1 className="text-2xl font-bold text-ink">Prediction Audit</h1>
      <p className="mt-1 text-[13px] text-muted">
        Every target the engine has called — graded against actual candles, with the reason for each
        outcome. This is the honest scoreboard: it shows where the system is accurate and where it
        needs work.
      </p>

      <div className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
        {stats.map(([label, value]) => (
          <div key={String(label)} className="rounded-lg border border-line-subtle bg-card p-3">
            <div className="text-[10.5px] uppercase tracking-wider text-faint">{label}</div>
            <div className="mt-1 text-lg font-bold text-ink">{String(value)}</div>
          </div>
        ))}
      </div>

      <div className="mt-6 space-y-3">
        {rows.length === 0 && (
          <p className="text-[13px] text-muted">
            No predictions recorded yet — one is snapshotted every time the engine issues a plan.
          </p>
        )}
        {rows.map((p) => {
          const st = STATUS_LABEL[p.status] ?? { text: p.status, cls: "bg-zinc-500/10 text-zinc-400" };
          const dt = p.created_at ? new Date(p.created_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : "—";
          return (
            <div key={p.id} className="rounded-lg border border-line-subtle bg-card p-4">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
                <span className={`rounded-full px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-wide ${st.cls}`}>
                  {st.text}
                </span>
                <span className={`text-[12px] font-semibold ${p.direction === "bearish" ? "text-red-500" : p.direction === "bullish" ? "text-emerald-500" : "text-muted"}`}>
                  {p.direction === "bearish" ? "SHORT" : p.direction === "bullish" ? "LONG" : p.direction || "—"}
                </span>
                <span className="text-[11px] text-faint">{dt} · {p.mode}</span>
              </div>

              <div className="mt-2.5 grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-5">
                <div><span className="text-[10.5px] uppercase tracking-wider text-faint">Entry</span><div className="text-[12.5px] text-ink">{fmtUsd(p.entry[0])}–{fmtUsd(p.entry[1])}</div></div>
                <div><span className="text-[10.5px] uppercase tracking-wider text-faint">Stop</span><div className="text-[12.5px] text-ink">{fmtUsd(p.stop)}</div></div>
                <div><span className="text-[10.5px] uppercase tracking-wider text-faint">Target 1</span><div className="text-[12.5px] text-ink">{fmtUsd(p.t1)}</div></div>
                <div><span className="text-[10.5px] uppercase tracking-wider text-faint">Target 2</span><div className="text-[12.5px] text-ink">{fmtUsd(p.t2)}</div></div>
                <div><span className="text-[10.5px] uppercase tracking-wider text-faint">Best move</span><div className="text-[12.5px] text-ink">{p.max_favorable == null ? "—" : `${fmtUsd(p.max_favorable)}/oz`}</div></div>
              </div>

              {p.reason && (
                <p className="mt-2.5 border-t border-line-subtle pt-2.5 text-[12px] leading-relaxed text-muted">
                  {p.reason}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
