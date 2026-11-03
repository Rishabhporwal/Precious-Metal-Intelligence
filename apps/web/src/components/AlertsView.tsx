"use client";

import { useCallback, useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Rule {
  id: number;
  kind: string;
  symbol: string;
  params: Record<string, unknown>;
  severity: string;
  cooldown_seconds: number;
  enabled: boolean;
}

interface AlertEvent {
  id: number;
  message: string;
  severity: string;
  delivered_telegram: boolean;
  fired_at: string;
  kind: string;
}

const KINDS = [
  ["price_above", "Price ≥ level"],
  ["price_below", "Price ≤ level"],
  ["sweep", "Liquidity sweep"],
  ["fvg", "FVG detected"],
  ["bos_choch", "MSS / CHoCH"],
  ["setup_new", "New composite setup"],
] as const;

export function AlertsView() {
  const [rules, setRules] = useState<Rule[]>([]);
  const [events, setEvents] = useState<AlertEvent[]>([]);
  const [telegramReady, setTelegramReady] = useState<boolean | null>(null);
  const [form, setForm] = useState({ kind: "price_above", level: "", cooldown: "3600", severity: "info" });

  const load = useCallback(async () => {
    const res = await fetch(`${API_URL}/api/v1/alerts`, { cache: "no-store" });
    if (res.ok) {
      const data = await res.json();
      setRules(data.rules);
      setEvents(data.recent_events);
    }
    // Telegram readiness: check whether any event has ever delivered OR probe env-backed config
    const health = await fetch(`${API_URL}/api/v1/macro/summary`, { cache: "no-store" }).catch(() => null);
    if (health?.ok) setTelegramReady(null); // unknown until first delivery attempt
  }, []);

  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), 30000);
    return () => clearInterval(t);
  }, [load]);

  const create = async () => {
    const params = form.level ? { level: Number(form.level) } : {};
    await fetch(`${API_URL}/api/v1/alerts`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        kind: form.kind,
        symbol: "XAUUSD",
        params,
        severity: form.severity,
        cooldown_seconds: Number(form.cooldown) || 3600,
      }),
    });
    await load();
  };

  const evaluate = async () => {
    await fetch(`${API_URL}/api/v1/alerts/evaluate`, { method: "POST" });
    await load();
  };

  const remove = async (id: number) => {
    await fetch(`${API_URL}/api/v1/alerts/${id}`, { method: "DELETE" });
    await load();
  };

  // browser notifications: poll recent events while the page is open
  useEffect(() => {
    if (typeof Notification === "undefined") return;
    if (Notification.permission === "default") void Notification.requestPermission();
  }, []);

  const lastEventId = events[0]?.id ?? 0;
  useEffect(() => {
    const seen = sessionStorage.getItem("pmi_last_alert_id");
    if (seen && events.length > 0 && events[0].id > Number(seen) && Notification.permission === "granted") {
      new Notification("PMI alert", { body: events[0].message });
    }
    if (events.length > 0) sessionStorage.setItem("pmi_last_alert_id", String(events[0].id));
  }, [events]);

  return (
    <div className="space-y-4">
      <div className="card p-5">
        <h3 className="card-title text-muted">New alert rule</h3>
        <div className="mt-2 flex flex-wrap items-center gap-2 num text-xs">
          <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}
            className="rounded border border-line bg-white/[0.02] px-2 py-1">
            {KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          {(form.kind === "price_above" || form.kind === "price_below") && (
            <input placeholder="price level" value={form.level} onChange={(e) => setForm({ ...form, level: e.target.value })}
              className="w-28 rounded border border-line bg-white/[0.02] px-2 py-1" />
          )}
          <select value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value })}
            className="rounded border border-line bg-white/[0.02] px-2 py-1">
            <option value="info">info</option>
            <option value="warning">warning</option>
            <option value="critical">critical</option>
          </select>
          <input placeholder="cooldown s" value={form.cooldown} onChange={(e) => setForm({ ...form, cooldown: e.target.value })}
            className="w-24 rounded border border-line bg-white/[0.02] px-2 py-1" />
          <button onClick={create} className="rounded border border-line px-3 py-1 hover:bg-white/[0.06]">add rule</button>
          <button onClick={evaluate} className="rounded border border-line px-3 py-1 hover:bg-white/[0.06]">evaluate now</button>
        </div>
        <p className="mt-2 text-[10px] text-faint">
          Delivery: Telegram (configure TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in .env) + browser
          notifications while this page is open. Cooldowns prevent repeated firing.
        </p>
      </div>

      {rules.length > 0 && (
        <div className="overflow-x-auto card">
          <table className="w-full text-left num text-[11px]">
            <thead className="bg-white/[0.02] text-muted">
              <tr>{["#", "Kind", "Symbol", "Params", "Severity", "Cooldown", ""].map((h) => <th key={h} className="px-3 py-2">{h}</th>)}</tr>
            </thead>
            <tbody>
              {rules.map((r) => (
                <tr key={r.id} className="border-t border-line">
                  <td className="px-3 py-2 text-muted">{r.id}</td>
                  <td className="px-3 py-2 text-ink-soft">{r.kind}</td>
                  <td className="px-3 py-2">{r.symbol}</td>
                  <td className="px-3 py-2 text-muted">{JSON.stringify(r.params)}</td>
                  <td className="px-3 py-2">{r.severity}</td>
                  <td className="px-3 py-2 text-muted">{r.cooldown_seconds}s</td>
                  <td className="px-3 py-2">
                    <button onClick={() => remove(r.id)} className="rounded border border-line px-2 py-0.5 text-[10px] hover:bg-white/[0.06]">delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {events.length > 0 && (
        <div className="space-y-1">
          <h3 className="card-title text-muted">Recent alert events</h3>
          {events.map((e) => (
            <div key={e.id} className="rounded border border-line bg-white/[0.02] px-3 py-2 num text-[10px]">
              <span className={e.severity === "critical" ? "text-down" : e.severity === "warning" ? "text-warn" : "text-ink-soft"}>
                {e.message}
              </span>
              <span className="float-right text-faint">
                {e.fired_at.slice(5, 16).replace("T", " ")}Z {e.delivered_telegram ? "· 📲" : "· local"}
              </span>
            </div>
          ))}
        </div>
      )}
      {rules.length === 0 && events.length === 0 && (
        <p className="card p-5 text-xs text-muted">
          No alert rules yet. The scheduler evaluates alerts every 2 minutes; browser notifications
          fire while this tab is open.
        </p>
      )}
    </div>
  );
}
