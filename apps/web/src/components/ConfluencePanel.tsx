"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Confluence {
  counts: Record<string, number>;
  score: number;
  interpretation: string;
  tone: string;
  supporting: string[];
  conflicting: string[];
  dedupe_note: string;
  method: string;
  evaluated_at: string | null;
}

export function ConfluencePanel({ interval = "1h", compact = false }: { interval?: string; compact?: boolean }) {
  const [c, setC] = useState<Confluence | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    let alive = true;
    fetch(`${API_URL}/api/v1/confluence/latest?symbol=XAUUSD&interval=${interval}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => {
        if (alive) setC(d);
      })
      .catch(() => {
        if (alive) setMissing(true);
      });
    return () => {
      alive = false;
    };
  }, [interval]);

  if (missing) {
    return (
      <p className="card p-5 text-xs text-muted">
        No confluence snapshot yet — the verdict engine runs every 15 minutes; refresh shortly.
      </p>
    );
  }
  if (!c) return <div className="card h-40 animate-pulse" />;

  const tonePill =
    c.tone === "strong" ? "pill-up" : c.tone === "moderate" ? "pill-gold" : "pill-warn";

  return (
    <div className="card p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className={`pill ${tonePill}`}>{c.interpretation}</span>
        {c.evaluated_at && (
          <span className="num text-[10px] text-faint">
            {new Date(c.evaluated_at).toISOString().slice(5, 16).replace("T", " ")}Z · score {c.score > 0 ? "+" : ""}
            {c.score}
          </span>
        )}
      </div>

      {!compact && (
        <div className="mt-4 grid grid-cols-3 gap-2 sm:grid-cols-4">
          {[
            ["Bullish", c.counts.bullish, "text-up"],
            ["Bearish", c.counts.bearish, "text-down"],
            ["Neutral", c.counts.neutral, "text-warn"],
            ["No signal", c.counts.no_signal, "text-faint"],
            ["Invalidated", c.counts.invalidated, "text-down"],
            ["Waiting", c.counts.waiting, "text-muted"],
            ["Insufficient", c.counts.insufficient_data, "text-faint"],
          ].map(([label, n, cls]) => (
            <div key={label as string} className="rounded-lg border border-line-subtle bg-raised px-3 py-2">
              <div className="text-[10px] uppercase tracking-wide text-faint">{label as string}</div>
              <div className={`num text-[16px] font-medium ${cls as string}`}>{n as number}</div>
            </div>
          ))}
        </div>
      )}

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <div className="card-title">Supporting evidence</div>
          <ul className="mt-1.5 space-y-1">
            {c.supporting.map((s, i) => (
              <li key={i} className="text-[12px] leading-relaxed text-muted">▲ {s}</li>
            ))}
            {c.supporting.length === 0 && <li className="text-[12px] text-faint">none</li>}
          </ul>
        </div>
        <div>
          <div className="card-title">Conflicting evidence</div>
          <ul className="mt-1.5 space-y-1">
            {c.conflicting.map((s, i) => (
              <li key={i} className="text-[12px] leading-relaxed text-muted">▼ {s}</li>
            ))}
            {c.conflicting.length === 0 && <li className="text-[12px] text-faint">none</li>}
          </ul>
        </div>
      </div>

      {!compact && (
        <p className="mt-4 text-[10px] leading-relaxed text-faint">
          {c.dedupe_note} · {c.method}
        </p>
      )}
    </div>
  );
}
