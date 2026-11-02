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
    return <p className="rounded-lg border border-red-900 bg-red-950/40 p-4 text-xs text-red-300">Paper API error: {error}</p>;
  }
  if (!account) return <div className="h-40 animate-pulse rounded-lg border border-neutral-800 bg-neutral-900/40" />;

  const pnlColor = (v: number | null) => (v == null ? "text-neutral-400" : v >= 0 ? "text-emerald-400" : "text-red-400");

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          ["Equity", `$${account.equity.toLocaleString("en-US")}`],
          ["Realized P&L", account.realized_pnl >= 0 ? `+$${account.realized_pnl.toFixed(2)}` : `-$${Math.abs(account.realized_pnl).toFixed(2)}`],
          ["Unrealized", account.unrealized_pnl >= 0 ? `+$${account.unrealized_pnl.toFixed(2)}` : `-$${Math.abs(account.unrealized_pnl).toFixed(2)}`],
          ["Win rate", account.stats.win_rate != null ? `${(account.stats.win_rate * 100).toFixed(0)}% (${account.stats.win_count}/${account.stats.closed_count})` : "—"],
        ].map(([k, v]) => (
          <div key={k} className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-3">
            <div className="text-[10px] text-neutral-500">{k}</div>
            <div className={`mt-1 font-mono text-lg font-semibold ${k !== "Equity" ? pnlColor(k === "Realized P&L" ? account.realized_pnl : account.unrealized_pnl) : "text-neutral-100"}`}>
              {v}
            </div>
          </div>
        ))}
      </div>

      <div className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-4">
        <h3 className="text-[10px] font-semibold uppercase tracking-widest text-neutral-500">New paper trade (simulated)</h3>
        <div className="mt-2 flex flex-wrap items-center gap-2 font-mono text-xs">
          <select
            value={form.direction}
            onChange={(e) => setForm({ ...form, direction: e.target.value })}
            className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1"
          >
            <option value="long">long</option>
            <option value="short">short</option>
          </select>
          <input placeholder="size oz (opt)" value={form.size} onChange={(e) => setForm({ ...form, size: e.target.value })}
            className="w-28 rounded border border-neutral-700 bg-neutral-900 px-2 py-1" />
          <input placeholder="stop (opt)" value={form.stop} onChange={(e) => setForm({ ...form, stop: e.target.value })}
            className="w-28 rounded border border-neutral-700 bg-neutral-900 px-2 py-1" />
          <input placeholder="target (opt)" value={form.target} onChange={(e) => setForm({ ...form, target: e.target.value })}
            className="w-28 rounded border border-neutral-700 bg-neutral-900 px-2 py-1" />
          <button onClick={open} disabled={busy}
            className="rounded border border-neutral-600 px-3 py-1 hover:bg-neutral-800 disabled:opacity-50">
            {busy ? "…" : "open (market)"}
          </button>
          <span className="text-[10px] text-neutral-600">
            no size = risk-based sizing (1% of equity ÷ stop distance)
          </span>
        </div>
      </div>

      {account.open_positions.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-neutral-800">
          <table className="w-full text-left font-mono text-[11px]">
            <thead className="bg-neutral-900 text-neutral-500">
              <tr>{["#", "Dir", "Size", "Entry", "Stop", "Target", "Now", "P&L", ""].map((h) => <th key={h} className="px-3 py-2">{h}</th>)}</tr>
            </thead>
            <tbody>
              {account.open_positions.map((t) => (
                <tr key={t.id} className="border-t border-neutral-800">
                  <td className="px-3 py-2 text-neutral-500">{t.id}</td>
                  <td className={t.direction === "long" ? "px-3 py-2 text-emerald-400" : "px-3 py-2 text-red-400"}>{t.direction}</td>
                  <td className="px-3 py-2">{t.size}</td>
                  <td className="px-3 py-2">{t.entry_price?.toFixed(2)}</td>
                  <td className="px-3 py-2">{t.stop?.toFixed(2) ?? "—"}</td>
                  <td className="px-3 py-2">{t.target?.toFixed(2) ?? "—"}</td>
                  <td className="px-3 py-2">{t.current_price?.toFixed(2)}</td>
                  <td className={`px-3 py-2 ${pnlColor(t.unrealized_or_realized_pnl)}`}>{t.unrealized_or_realized_pnl?.toFixed(2)}</td>
                  <td className="px-3 py-2">
                    <button onClick={() => close(t.id)} disabled={busy} className="rounded border border-neutral-700 px-2 py-0.5 text-[10px] hover:bg-neutral-800">close</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {account.closed_trades.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-neutral-800">
          <table className="w-full text-left font-mono text-[11px]">
            <thead className="bg-neutral-900 text-neutral-500">
              <tr>{["#", "Dir", "Entry", "Exit", "Reason", "P&L"].map((h) => <th key={h} className="px-3 py-2">{h}</th>)}</tr>
            </thead>
            <tbody>
              {account.closed_trades.map((t) => (
                <tr key={t.id} className="border-t border-neutral-800">
                  <td className="px-3 py-2 text-neutral-500">{t.id}</td>
                  <td className="px-3 py-2">{t.direction}</td>
                  <td className="px-3 py-2">{t.entry_price?.toFixed(2)}</td>
                  <td className="px-3 py-2">{t.exit_price?.toFixed(2)}</td>
                  <td className="px-3 py-2 text-neutral-500">{t.exit_reason}</td>
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
