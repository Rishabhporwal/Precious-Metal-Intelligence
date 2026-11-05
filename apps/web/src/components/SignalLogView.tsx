"use client";

import { useCallback, useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Stat {
  signal_type: string;
  total: number;
  graded: number;
  avg_r: number | null;
  win_rate: number | null;
  avg_mfe_r: number | null;
  avg_mae_r: number | null;
}

interface HistSignal {
  id: number;
  signal_type: string;
  created_at: string;
  price: string | number;
  score: number | string | null;
  regime: string;
  graded: boolean;
  exit_reason: string | null;
  r_multiple: string | number | null;
}

interface Missed {
  move_time: string;
  move_pct: number;
  direction: string;
  detected_by: string[];
  blocked_by: string;
}

const pill = (t: string) =>
  t.includes("BUY") ? "pill-up" : t.includes("SELL") ? "pill-down" : t === "WAIT" ? "pill-warn" : "";

const blockedLabel: Record<string, string> = {
  no_signal_in_window: "no signal generated",
  signal_wait: "signal was WAIT",
  signal_no_trade: "signal was NO TRADE",
  signal_opposite: "signal pointed the other way",
  covered_by_signal: "covered",
};

export function SignalLogView() {
  const [interval, setInterval_] = useState<"1h" | "1day">("1h");
  const [stats, setStats] = useState<Stat[]>([]);
  const [history, setHistory] = useState<HistSignal[]>([]);
  const [missed, setMissed] = useState<Missed[] | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (tf: string) => {
    const [s, h, m] = await Promise.all([
      fetch(`${API_URL}/api/v1/signals/stats?symbol=XAUUSD&interval=${tf}`).then((r) => (r.ok ? r.json() : null)),
      fetch(`${API_URL}/api/v1/signals/history?symbol=XAUUSD&interval=${tf}&limit=30`).then((r) => (r.ok ? r.json() : null)),
      fetch(`${API_URL}/api/v1/signals/missed?symbol=XAUUSD&interval=${tf}`).then((r) => (r.ok ? r.json() : null)),
    ]);
    setStats(s?.stats ?? []);
    setHistory(h?.signals ?? []);
    setMissed(m?.missed ?? []);
  }, []);

  useEffect(() => {
    void load(interval);
  }, [interval, load]);

  const scanMissed = async () => {
    setBusy(true);
    try {
      await fetch(`${API_URL}/api/v1/signals/missed-scan?symbol=XAUUSD&interval=${interval}&lookback_days=30`, { method: "POST" });
      await load(interval);
    } finally {
      setBusy(false);
    }
  };

  const fmtR = (v: string | number | null) =>
    v == null ? "—" : `${Number(v) > 0 ? "+" : ""}${Number(v).toFixed(2)}R`;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {(["1h", "1day"] as const).map((tf) => (
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
        <button onClick={scanMissed} disabled={busy} className="btn btn-sm">
          {busy ? "scanning…" : "Scan for missed moves (30d)"}
        </button>
      </div>

      {/* precision per signal type (§14) */}
      <div className="card overflow-x-auto">
        <div className="px-4 pt-4 card-title">Signal evaluation — graded against actual outcomes</div>
        <table className="data-table mt-2">
          <thead>
            <tr>
              <th>Signal</th><th>Total</th><th>Graded</th><th>Win rate</th><th>Avg R</th><th>Avg MFE</th><th>Avg MAE</th>
            </tr>
          </thead>
          <tbody>
            {stats.map((s) => (
              <tr key={s.signal_type}>
                <td className="font-medium text-ink">{s.signal_type.replace("_", " ")}</td>
                <td className="num">{s.total}</td>
                <td className="num">{s.graded}</td>
                <td className="num">{s.win_rate != null ? `${(s.win_rate * 100).toFixed(0)}%` : "—"}</td>
                <td className={`num ${Number(s.avg_r) > 0 ? "text-up" : Number(s.avg_r) < 0 ? "text-down" : ""}`}>
                  {s.avg_r != null ? `${s.avg_r > 0 ? "+" : ""}${s.avg_r.toFixed(2)}R` : "—"}
                </td>
                <td className="num">{s.avg_mfe_r != null ? `${s.avg_mfe_r.toFixed(2)}R` : "—"}</td>
                <td className="num">{s.avg_mae_r != null ? `${s.avg_mae_r.toFixed(2)}R` : "—"}</td>
              </tr>
            ))}
            {stats.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-5 text-center text-muted">No graded signals yet — outcomes accrue as signals expire.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* history */}
      <div className="card overflow-x-auto">
        <div className="px-4 pt-4 card-title">Signal history — timestamped at decision time</div>
        <table className="data-table mt-2">
          <thead>
            <tr><th>When</th><th>Signal</th><th>Score</th><th>Price</th><th>Regime</th><th>Outcome</th></tr>
          </thead>
          <tbody>
            {history.map((h) => (
              <tr key={h.id}>
                <td className="num text-[11px] text-faint">{h.created_at.slice(5, 16).replace("T", " ")}</td>
                <td><span className={`pill ${pill(h.signal_type)}`}>{h.signal_type.replace("_", " ")}</span></td>
                <td className="num">{h.score ?? "—"}</td>
                <td className="num">{Number(h.price).toFixed(2)}</td>
                <td className="text-muted">{h.regime}</td>
                <td className="text-muted">
                  {h.graded ? `${h.exit_reason ?? "—"} · ${fmtR(h.r_multiple)}` : "open"}
                </td>
              </tr>
            ))}
            {history.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-5 text-center text-muted">No signals yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* missed opportunities (§10) */}
      <div className="card overflow-x-auto">
        <div className="px-4 pt-4 card-title">Missed-opportunity analysis — major moves (≥1.5% in 24h) without an aligned signal</div>
        <table className="data-table mt-2">
          <thead>
            <tr><th>Move time</th><th>Move</th><th>Direction</th><th>Strategies that fired before it</th><th>Why missed</th></tr>
          </thead>
          <tbody>
            {(missed ?? []).map((m, i) => (
              <tr key={i}>
                <td className="num text-[11px] text-faint">{m.move_time.slice(5, 16).replace("T", " ")}</td>
                <td className={`num ${m.direction === "up" ? "text-up" : "text-down"}`}>
                  {m.move_pct > 0 ? "+" : ""}{m.move_pct.toFixed(2)}%
                </td>
                <td className="text-muted">{m.direction}</td>
                <td className="text-muted">{m.detected_by.length ? m.detected_by.join(", ") : "none fired"}</td>
                <td><span className="pill pill-warn">{blockedLabel[m.blocked_by] ?? m.blocked_by}</span></td>
              </tr>
            ))}
            {missed !== null && missed.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-5 text-center text-muted">
                No missed moves in the scan window — or the scan hasn't run yet (button above).
              </td></tr>
            )}
          </tbody>
        </table>
        <p className="px-4 pb-4 pt-2 text-[10px] leading-relaxed text-faint">
          Coverage facts only — never "would have made X". Use the blocking reasons to justify
          parameter changes with evidence, not hindsight.
        </p>
      </div>
    </div>
  );
}
