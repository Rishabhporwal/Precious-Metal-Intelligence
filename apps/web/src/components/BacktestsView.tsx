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
          className="rounded border border-line px-3 py-1.5 num text-xs text-ink-soft hover:bg-white/[0.06] disabled:opacity-50"
        >
          {busy ? "running…" : "Run backtest: composite on XAUUSD 1H (all stored history)"}
        </button>
        {msg && <span className="text-[10px] text-muted">{msg}</span>}
      </div>

      {runs.length > 0 && (
        <div className="overflow-x-auto card">
          <table className="w-full text-left num text-[11px]">
            <thead className="bg-white/[0.02] text-muted">
              <tr>{["#", "Window", "Trades", "Win rate", "PF", "Expectancy", "Max DD", "OOS exp.", "Leak excl.", ""].map((h) => <th key={h} className="px-3 py-2">{h}</th>)}</tr>
            </thead>
            <tbody>
              {runs.map((r) => {
                const m = r.metrics as Record<string, number | null>;
                const o = (r.oos_metrics ?? {}) as Record<string, number | null>;
                return (
                  <tr key={r.id} className="border-t border-line">
                    <td className="px-3 py-2 text-muted">{r.id}</td>
                    <td className="px-3 py-2 text-[10px] text-muted">
                      {r.data_start?.slice(0, 10)} → {r.data_end?.slice(0, 10)}
                    </td>
                    <td className="px-3 py-2">{fmt(m.closed_trades)}</td>
                    <td className="px-3 py-2">{m.win_rate != null ? `${(Number(m.win_rate) * 100).toFixed(0)}%` : "—"}</td>
                    <td className="px-3 py-2">{fmt(m.profit_factor)}</td>
                    <td className="px-3 py-2">{fmt(m.expectancy_r, "R")}</td>
                    <td className="px-3 py-2 text-down">{m.max_drawdown_pct != null ? `${m.max_drawdown_pct}%` : "—"}</td>
                    <td className="px-3 py-2">{fmt(o.expectancy_r, "R")}</td>
                    <td className="px-3 py-2 text-warn">{r.leakage_excluded}</td>
                    <td className="px-3 py-2">
                      <button onClick={() => openRun(r.id)} className="rounded border border-line px-2 py-0.5 text-[10px] hover:bg-white/[0.06]">detail</button>
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
          <div className="card p-5">
            <h3 className="card-title text-muted">
              Run #{detail.id} — cost model + assumptions
            </h3>
            <p className="mt-2 num text-[10px] text-muted">
              {JSON.stringify(detail.cost_model)}
            </p>
            <ul className="mt-2 list-disc pl-4 text-[10px] leading-relaxed text-muted">
              {(detail.assumptions ?? []).map((a, i) => <li key={i}>{a}</li>)}
            </ul>
          </div>
          <div className="overflow-x-auto card">
            <table className="w-full text-left num text-[11px]">
              <thead className="bg-white/[0.02] text-muted">
                <tr>{["Dir", "Entry", "R (net)", "P&L", "Exit", "Segment"].map((h) => <th key={h} className="px-3 py-2">{h}</th>)}</tr>
              </thead>
              <tbody>
                {detail.trades.map((t, i) => (
                  <tr key={i} className="border-t border-line">
                    <td className={`px-3 py-2 ${t.direction === "long" ? "text-up" : "text-down"}`}>{t.direction}</td>
                    <td className="px-3 py-2 text-muted">{t.entry_time.slice(5, 16).replace("T", " ")}</td>
                    <td className={`px-3 py-2 ${Number(t.r_multiple) >= 0 ? "text-up" : "text-down"}`}>{t.r_multiple ?? "—"}</td>
                    <td className="px-3 py-2">{t.pnl ?? "—"}</td>
                    <td className="px-3 py-2 text-muted">{t.exit_reason}</td>
                    <td className="px-3 py-2 text-faint">{t.segment.toUpperCase()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {runs.length === 0 && !detail && (
        <p className="card p-5 text-xs text-muted">
          No backtests yet. Each run: leakage-gated detections → limit entry → pessimistic stops →
          50% partial at 1R → breakeven stop → 2R exit, costs deducted, IS/OOS split reported separately.
        </p>
      )}
    </div>
  );
}
