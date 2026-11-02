"use client";

import { useCallback, useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface RunSummary {
  id: number;
  interval: string;
  strategy_id: string;
  data_start: string | null;
  data_end: string | null;
  metrics: Record<string, unknown>;
  oos_metrics: Record<string, unknown> | null;
  leakage_excluded: number;
  created_at: string | null;
}

interface RunDetail extends RunSummary {
  trades: { direction: string; entry_time: string; r_multiple: string | null; pnl: string | null; exit_reason: string; segment: string }[];
  cost_model: Record<string, number>;
  assumptions: string[];
}

export function BacktestsView() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await fetch(`${API_URL}/api/v1/backtests`, { cache: "no-store" });
    if (res.ok) setRuns((await res.json()).runs);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const runBacktest = async () => {
    setBusy(true);
    setMsg("running (may take ~1 min on 4,000 candles)…");
    try {
      const res = await fetch(`${API_URL}/api/v1/backtests`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ symbol: "XAUUSD", interval: "1h" }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMsg(`Failed: ${data.detail ?? res.status}`);
      } else {
        setMsg(`Run #${data.run_id} complete — leakage excluded: ${data.leakage_excluded}`);
        await load();
        const d = await fetch(`${API_URL}/api/v1/backtests/${data.run_id}`).then((r) => r.json());
        setDetail(d);
      }
    } finally {
      setBusy(false);
    }
  };

  const openRun = async (id: number) => {
    const d = await fetch(`${API_URL}/api/v1/backtests/${id}`).then((r) => r.json());
    setDetail(d);
  };

  const fmt = (v: unknown, suffix = "") => (v == null ? "—" : `${v}${suffix}`);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <button
          onClick={runBacktest}
          disabled={busy}
          className="rounded border border-neutral-600 px-3 py-1.5 font-mono text-xs text-neutral-200 hover:bg-neutral-800 disabled:opacity-50"
        >
          {busy ? "running…" : "Run backtest: composite on XAUUSD 1H (all stored history)"}
        </button>
        {msg && <span className="text-[10px] text-neutral-500">{msg}</span>}
      </div>

      {runs.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-neutral-800">
          <table className="w-full text-left font-mono text-[11px]">
            <thead className="bg-neutral-900 text-neutral-500">
              <tr>{["#", "Window", "Trades", "Win rate", "PF", "Expectancy", "Max DD", "OOS exp.", "Leak excl.", ""].map((h) => <th key={h} className="px-3 py-2">{h}</th>)}</tr>
            </thead>
            <tbody>
              {runs.map((r) => {
                const m = r.metrics as Record<string, number | null>;
                const o = (r.oos_metrics ?? {}) as Record<string, number | null>;
                return (
                  <tr key={r.id} className="border-t border-neutral-800">
                    <td className="px-3 py-2 text-neutral-500">{r.id}</td>
                    <td className="px-3 py-2 text-[10px] text-neutral-400">
                      {r.data_start?.slice(0, 10)} → {r.data_end?.slice(0, 10)}
                    </td>
                    <td className="px-3 py-2">{fmt(m.closed_trades)}</td>
                    <td className="px-3 py-2">{m.win_rate != null ? `${(Number(m.win_rate) * 100).toFixed(0)}%` : "—"}</td>
                    <td className="px-3 py-2">{fmt(m.profit_factor)}</td>
                    <td className="px-3 py-2">{fmt(m.expectancy_r, "R")}</td>
                    <td className="px-3 py-2 text-red-400">{m.max_drawdown_pct != null ? `${m.max_drawdown_pct}%` : "—"}</td>
                    <td className="px-3 py-2">{fmt(o.expectancy_r, "R")}</td>
                    <td className="px-3 py-2 text-amber-400">{r.leakage_excluded}</td>
                    <td className="px-3 py-2">
                      <button onClick={() => openRun(r.id)} className="rounded border border-neutral-700 px-2 py-0.5 text-[10px] hover:bg-neutral-800">detail</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {detail && (
        <div className="space-y-3">
          <div className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-4">
            <h3 className="text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
              Run #{detail.id} — cost model + assumptions
            </h3>
            <p className="mt-2 font-mono text-[10px] text-neutral-500">
              {JSON.stringify(detail.cost_model)}
            </p>
            <ul className="mt-2 list-disc pl-4 text-[10px] leading-relaxed text-neutral-500">
              {(detail.assumptions ?? []).map((a, i) => <li key={i}>{a}</li>)}
            </ul>
          </div>
          <div className="overflow-x-auto rounded-lg border border-neutral-800">
            <table className="w-full text-left font-mono text-[11px]">
              <thead className="bg-neutral-900 text-neutral-500">
                <tr>{["Dir", "Entry", "R (net)", "P&L", "Exit", "Segment"].map((h) => <th key={h} className="px-3 py-2">{h}</th>)}</tr>
              </thead>
              <tbody>
                {detail.trades.map((t, i) => (
                  <tr key={i} className="border-t border-neutral-800">
                    <td className={`px-3 py-2 ${t.direction === "long" ? "text-emerald-400" : "text-red-400"}`}>{t.direction}</td>
                    <td className="px-3 py-2 text-neutral-500">{t.entry_time.slice(5, 16).replace("T", " ")}</td>
                    <td className={`px-3 py-2 ${Number(t.r_multiple) >= 0 ? "text-emerald-400" : "text-red-400"}`}>{t.r_multiple ?? "—"}</td>
                    <td className="px-3 py-2">{t.pnl ?? "—"}</td>
                    <td className="px-3 py-2 text-neutral-500">{t.exit_reason}</td>
                    <td className="px-3 py-2 text-neutral-600">{t.segment.toUpperCase()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {runs.length === 0 && !detail && (
        <p className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-4 text-xs text-neutral-400">
          No backtests yet. Each run: leakage-gated detections → limit entry → pessimistic stops →
          50% partial at 1R → breakeven stop → 2R exit, costs deducted, IS/OOS split reported separately.
        </p>
      )}
    </div>
  );
}
