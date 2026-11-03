"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Quote {
  price: number;
  prev?: number;
}

/** Live XAU/USD chip — polls the gateway quote every 30s. */
export function LivePriceChip({ compact = false }: { compact?: boolean }) {
  const [q, setQ] = useState<Quote | null>(null);
  const [prev, setPrev] = useState<number | null>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const res = await fetch(`${API_URL}/api/v1/markets/XAUUSD/quote`, { cache: "no-store" });
        if (!res.ok) throw new Error(String(res.status));
        const d = await res.json();
        if (!alive) return;
        setQ((old) => {
          if (old && old.price !== d.price) setPrev(old.price);
          return { price: d.price };
        });
        setErr(false);
      } catch {
        if (alive) setErr(true);
      }
    };
    void tick();
    const id = setInterval(tick, 30_000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const direction = q && prev ? (q.price > prev ? "up" : q.price < prev ? "down" : "") : "";
  const tick = direction === "up" ? "▲" : direction === "down" ? "▼" : "";

  return (
    <div
      className={`pill ${direction === "up" ? "pill-up" : direction === "down" ? "pill-down" : ""}`}
      title="XAU/USD spot — streamed from stored quotes"
    >
      <span className="dot dot-live" />
      <span className="text-[10px] uppercase tracking-wider text-faint">XAU</span>
      {q ? (
        <span className={`num text-[11.5px] font-medium ${direction === "up" ? "text-up" : direction === "down" ? "text-down" : "text-ink"}`}>
          {tick} {Number(q.price).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </span>
      ) : err ? (
        <span className="text-[11px] text-faint">offline</span>
      ) : (
        <span className="text-[11px] text-faint">…</span>
      )}
      {!compact && <span className="text-[10px] text-faint">USD</span>}
    </div>
  );
}
