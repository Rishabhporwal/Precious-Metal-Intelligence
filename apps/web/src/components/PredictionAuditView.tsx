"use client";

import { useEffect, useState } from "react";

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
  t1_hit_at: string | null;
  t2_hit_at: string | null;
  stopped_at: string | null;
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

const STATUS_LABEL: Record<string, { text: string; cls: string }> = {
  pending: { text: "In progress", cls: "bg-blue-500/10 text-blue-500" },
  hit_t1: { text: "T1 hit", cls: "bg-emerald-500/10 text-emerald-500" },
  hit_t2: { text: "T1+T2 hit", cls: "bg-emerald-500/15 text-emerald-400" },
  stopped: { text: "Stopped out", cls: "bg-red-500/10 text-red-500" },
  stopped_pre_entry: { text: "Never filled", cls: "bg-amber-500/10 text-amber-500" },
  superseded: { text: "Superseded", cls: "bg-zinc-500/10 text-zinc-400" },
  expired: { text: "Expired", cls: "bg-zinc-500/10 text-zinc-400" },
};

const fmt = (v: number | null | undefined) =>
  v == null ? "—" : `$${v.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;

export default function PredictionAuditView() {
  const [rows, setRows] = useState<Prediction[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [a, s] = await Promise.all([
          fetch("/api/v1/predictions/audit?limit=50").then((r) => r.json()),
          fetch("/api/v1/predictions/summary").then((r) => r.json()),
        ]);
        if (!alive) return;
        setRows(a.predictions ?? []);
        setSummary(s);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  if (loading) return <p className="text-muted">Loading prediction audit…</p>;

  const stats = summary
    ? [
        ["Predictions made", summary.total],
        ["Still in progress", summary.pending],
        ["Reached T1", summary.hit_t1 + summary.hit_t2],
        ["Reached T2", summary.hit_t2],
        ["Stopped out", summary.stopped],
        ["Superseded", summary.superseded ?? 0],
        ["Expired", summary.expired],
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
                <div><span className="text-[10.5px] uppercase tracking-wider text-faint">Entry</span><div className="text-[12.5px] text-ink">{fmt(p.entry[0])}–{fmt(p.entry[1])}</div></div>
                <div><span className="text-[10.5px] uppercase tracking-wider text-faint">Stop</span><div className="text-[12.5px] text-ink">{fmt(p.stop)}</div></div>
                <div><span className="text-[10.5px] uppercase tracking-wider text-faint">Target 1</span><div className="text-[12.5px] text-ink">{fmt(p.t1)}</div></div>
                <div><span className="text-[10.5px] uppercase tracking-wider text-faint">Target 2</span><div className="text-[12.5px] text-ink">{fmt(p.t2)}</div></div>
                <div><span className="text-[10.5px] uppercase tracking-wider text-faint">Best move</span><div className="text-[12.5px] text-ink">{p.max_favorable == null ? "—" : `${fmt(p.max_favorable)}/oz`}</div></div>
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
