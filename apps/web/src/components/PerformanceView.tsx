"use client";

import { useCallback, useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const NAMES: Record<string, string> = {
  smc_liquidity_sweep: "Liquidity Sweep",
  smc_eqh_eql: "Equal Highs / Lows",
  ict_pdh_pdl: "Prev Day/Week H-L",
  ict_asian_range: "Asian Range",
  ict_mss: "MSS / CHoCH",
  smc_fvg: "Fair Value Gap",
  smc_order_block: "Order Block",
  smc_breaker: "Breaker Block",
  smc_displacement: "Displacement",
  smc_premium_discount: "Premium / Discount",
  ict_fib_ote: "Fibonacci / OTE",
  cross_market_smt: "SMT Divergence",
  price_action_failed_breakout: "Failed Breakout",
  wyckoff_spring: "Wyckoff Spring",
  wyckoff_upthrust: "Wyckoff Upthrust",
};

interface StratSummary {
  strategy_id: string;
  run_id: number;
  data_start: string | null;
  data_end: string | null;
  metrics: Record<string, number | null>;
  oos_metrics: Record<string, number | null>;
  leakage_excluded: number;
  created_at: string | null;
}

const TIMEFRAMES = ["15min", "1h", "4h", "1day"] as const;

export function PerformanceView() {
  const [interval, setInterval_] = useState<(typeof TIMEFRAMES)[number]>("1h");
  const [rows, setRows] = useState<StratSummary[]>([]);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async (tf: string) => {
    const res = await fetch(`${API_URL}/api/v1/performance/summary?symbol=XAUUSD&interval=${tf}`, { cache: "no-store" });
    if (res.ok) setRows((await res.json()).strategies);
    setLoaded(true);
  }, []);

  useEffect(() => {
    void load(interval);
  }, [interval, load]);

  const runAll = async () => {
    setBusy(true);
    try {
      await fetch(`${API_URL}/api/v1/performance/evaluate?symbol=XAUUSD&interval=${interval}&limit=1200`, {
        method: "POST",
      });
      await load(interval);
    } finally {
      setBusy(false);
    }
  };

  const fmt = (v: unknown, suffix = "") => (v == null ? "—" : `${v}${suffix}`);
  const pct = (v: unknown) => (v == null ? "—" : `${(Number(v) * 100).toFixed(0)}%`);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {TIMEFRAMES.map((tf) => (
          <button
            key={tf}
            onClick={() => setInterval_(tf)}
            className={`rounded-md px-2.5 py-1 text-[12px] font-medium transition-all ${
              interval === tf ? "bg-gold-dim text-gold-bright" : "text-muted hover:bg-black/5 hover:text-ink dark:hover:bg-white/5"
            }`}
          >
            {tf.toUpperCase()}
          </button>
        ))}
        <div className="flex-1" />
        <button onClick={runAll} disabled={busy} className="btn btn-sm">
          {busy ? "backtesting all strategies (leakage-gated, takes minutes)…" : "Run / refresh all backtests"}
        </button>
      </div>

      {loaded && rows.length === 0 && (
        <p className="card p-5 text-xs text-muted">
          No backtests stored for {interval.toUpperCase()} yet. Run all backtests to generate real,
          leakage-gated results — nothing here is estimated.
        </p>
      )}

      {rows.length > 0 && (
        <div className="card overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Strategy</th>
                <th>Trades</th>
                <th>Win rate</th>
                <th>Profit factor</th>
                <th>Expectancy</th>
                <th>Avg win</th>
                <th>Avg loss</th>
                <th>Max DD</th>
                <th>Avg hold</th>
                <th>OOS trades</th>
                <th>OOS expectancy</th>
                <th>Window</th>
              </tr>
            </thead>
            <tbody>
              {rows
                .slice()
                .sort((a, b) => Number(b.metrics?.expectancy_r ?? -99) - Number(a.metrics?.expectancy_r ?? -99))
                .map((r) => {
                  const m = (r.metrics ?? {}) as Record<string, number | null>;
                  const o = (r.oos_metrics ?? {}) as Record<string, number | null>;
                  const exp = m.expectancy_r;
                  return (
                    <tr key={r.strategy_id}>
                      <td className="font-medium text-ink">{NAMES[r.strategy_id] ?? r.strategy_id}</td>
                      <td className="num">{fmt(m.closed_trades)}</td>
                      <td className="num">{pct(m.win_rate)}</td>
                      <td className="num">{fmt(m.profit_factor)}</td>
                      <td className={`num ${Number(exp) > 0 ? "text-up" : Number(exp) < 0 ? "text-down" : ""}`}>
                        {fmt(exp, "R")}
                      </td>
                      <td className="num">{fmt(m.avg_win_r, "R")}</td>
                      <td className="num">{fmt(m.avg_loss_r, "R")}</td>
                      <td className="num">{fmt(m.max_drawdown_pct, "%")}</td>
                      <td className="num">{fmt(m.avg_hold_hours, "h")}</td>
                      <td className="num">{fmt(o.closed_trades)}</td>
                      <td className="num">{fmt(o.expectancy_r, "R")}</td>
                      <td className="num text-[10px] text-faint">
                        {r.data_start} → {r.data_end}
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-[10.5px] leading-relaxed text-faint">
        Every number comes from the leakage-gated backtester: detections re-verified on data prefixes,
        pessimistic intrabar fills (stop wins), spread + slippage deducted, IS/OOS split at 60/40.
        Small trade counts are honest — strategies have limited live detection history. Past results
        do not guarantee future performance.
      </p>
    </div>
  );
}
