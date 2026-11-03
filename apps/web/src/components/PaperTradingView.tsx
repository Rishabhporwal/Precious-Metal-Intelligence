"use client";

import { useCallback, useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Trade {
  id: number;
  direction: string;
  size: number | null;
  entry_price: number | null;
  entry_time: string | null;
  stop: number | null;
  target: number | null;
  exit_price: number | null;
  exit_reason: string | null;
  status: string;
  current_price: number | null;
  unrealized_or_realized_pnl: number | null;
}

interface Account {
  name: string;
  initial_balance: number;
  equity: number;
  realized_pnl: number;
  unrealized_pnl: number;
  open_positions: Trade[];
  closed_trades: Trade[];
  stats: { closed_count: number; win_count: number; win_rate: number | null };
}

export function PaperTradingView() {
  const [account, setAccount] = useState<Account | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ direction: "long", size: "", stop: "", target: "" });

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/paper/accounts`, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setAccount(await res.json());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed");
    }
  }, []);

  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), 30000);
    return () => clearInterval(t);
  }, [load]);

  const open = async () => {
    setBusy(true);
    try {
      const body: Record<string, unknown> = { symbol: "XAUUSD", direction: form.direction };
      if (form.size) body.size = Number(form.size);
      if (form.stop) body.stop = Number(form.stop);
      if (form.target) body.target = Number(form.target);
      const res = await fetch(`${API_URL}/api/v1/paper/trades`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) setError(data.detail ?? `HTTP ${res.status}`);
      else await load();
    } finally {
      setBusy(false);
    }
  };

  const close = async (id: number) => {
    setBusy(true);
    try {
      await fetch(`${API_URL}/api/v1/paper/trades/${id}/close`, { method: "POST" });
      await load();
    } finally {
      setBusy(false);
    }
  };

  if (error && !account) {
    return <p className="card p-5 border-[rgba(246,70,93,0.3)] bg-[var(--down-dim)] text-xs text-down">Paper API error: {error}</p>;
  }
  if (!account) return <div className="h-40 animate-pulse card animate-pulse opacity-60" />;

  const pnlColor = (v: number | null) => (v == null ? "text-muted" : v >= 0 ? "text-up" : "text-down");

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          ["Equity", `$${account.equity.toLocaleString("en-US")}`],
          ["Realized P&L", account.realized_pnl >= 0 ? `+$${account.realized_pnl.toFixed(2)}` : `-$${Math.abs(account.realized_pnl).toFixed(2)}`],
          ["Unrealized", account.unrealized_pnl >= 0 ? `+$${account.unrealized_pnl.toFixed(2)}` : `-$${Math.abs(account.unrealized_pnl).toFixed(2)}`],
          ["Win rate", account.stats.win_rate != null ? `${(account.stats.win_rate * 100).toFixed(0)}% (${account.stats.win_count}/${account.stats.closed_count})` : "—"],
        ].map(([k, v]) => (
          <div key={k} className="card bg-white/[0.02] p-3">
            <div className="text-[10px] text-muted">{k}</div>
            <div className={`mt-1 num text-lg font-semibold ${k !== "Equity" ? pnlColor(k === "Realized P&L" ? account.realized_pnl : account.unrealized_pnl) : "text-ink"}`}>
              {v}
            </div>
          </div>
        ))}
      </div>

      <div className="card p-5">
        <h3 className="card-title text-muted">New paper trade (simulated)</h3>
        <div className="mt-2 flex flex-wrap items-center gap-2 num text-xs">
          <select
            value={form.direction}
            onChange={(e) => setForm({ ...form, direction: e.target.value })}
            className="rounded border border-line bg-white/[0.02] px-2 py-1"
          >
            <option value="long">long</option>
            <option value="short">short</option>
          </select>
          <input placeholder="size oz (opt)" value={form.size} onChange={(e) => setForm({ ...form, size: e.target.value })}
            className="w-28 rounded border border-line bg-white/[0.02] px-2 py-1" />
          <input placeholder="stop (opt)" value={form.stop} onChange={(e) => setForm({ ...form, stop: e.target.value })}
            className="w-28 rounded border border-line bg-white/[0.02] px-2 py-1" />
          <input placeholder="target (opt)" value={form.target} onChange={(e) => setForm({ ...form, target: e.target.value })}
            className="w-28 rounded border border-line bg-white/[0.02] px-2 py-1" />
          <button onClick={open} disabled={busy}
            className="rounded border border-line px-3 py-1 hover:bg-white/[0.06] disabled:opacity-50">
            {busy ? "…" : "open (market)"}
          </button>
          <span className="text-[10px] text-faint">
            no size = risk-based sizing (1% of equity ÷ stop distance)
          </span>
        </div>
      </div>

      {account.open_positions.length > 0 && (
        <div className="overflow-x-auto card">
          <table className="w-full text-left num text-[11px]">
            <thead className="bg-white/[0.02] text-muted">
              <tr>{["#", "Dir", "Size", "Entry", "Stop", "Target", "Now", "P&L", ""].map((h) => <th key={h} className="px-3 py-2">{h}</th>)}</tr>
            </thead>
            <tbody>
              {account.open_positions.map((t) => (
                <tr key={t.id} className="border-t border-line">
                  <td className="px-3 py-2 text-muted">{t.id}</td>
                  <td className={t.direction === "long" ? "px-3 py-2 text-up" : "px-3 py-2 text-down"}>{t.direction}</td>
                  <td className="px-3 py-2">{t.size}</td>
                  <td className="px-3 py-2">{t.entry_price?.toFixed(2)}</td>
                  <td className="px-3 py-2">{t.stop?.toFixed(2) ?? "—"}</td>
                  <td className="px-3 py-2">{t.target?.toFixed(2) ?? "—"}</td>
                  <td className="px-3 py-2">{t.current_price?.toFixed(2)}</td>
                  <td className={`px-3 py-2 ${pnlColor(t.unrealized_or_realized_pnl)}`}>{t.unrealized_or_realized_pnl?.toFixed(2)}</td>
                  <td className="px-3 py-2">
                    <button onClick={() => close(t.id)} disabled={busy} className="rounded border border-line px-2 py-0.5 text-[10px] hover:bg-white/[0.06]">close</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {account.closed_trades.length > 0 && (
        <div className="overflow-x-auto card">
          <table className="w-full text-left num text-[11px]">
            <thead className="bg-white/[0.02] text-muted">
              <tr>{["#", "Dir", "Entry", "Exit", "Reason", "P&L"].map((h) => <th key={h} className="px-3 py-2">{h}</th>)}</tr>
            </thead>
            <tbody>
              {account.closed_trades.map((t) => (
                <tr key={t.id} className="border-t border-line">
                  <td className="px-3 py-2 text-muted">{t.id}</td>
                  <td className="px-3 py-2">{t.direction}</td>
                  <td className="px-3 py-2">{t.entry_price?.toFixed(2)}</td>
                  <td className="px-3 py-2">{t.exit_price?.toFixed(2)}</td>
                  <td className="px-3 py-2 text-muted">{t.exit_reason}</td>
                  <td className={`px-3 py-2 ${pnlColor(t.unrealized_or_realized_pnl)}`}>{t.unrealized_or_realized_pnl?.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
