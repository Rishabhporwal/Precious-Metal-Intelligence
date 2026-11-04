"use client";

import { useCallback, useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface NewsEvent {
  id: number;
  title: string;
  category: string;
  region: string | null;
  entities: string[];
  importance: string;
  gold_impact: string;
  verification: string;
  sources_count: number;
  sources: string[];
  first_seen: string | null;
  last_update: string | null;
  articles: { title: string; source: string; url: string; published_at: string | null; sentiment: string | null }[];
}

const verifyPill = (v: string) =>
  v === "CONFIRMED" ? "pill-up" : v === "DEVELOPING" ? "pill-warn" : v === "REPORTED" ? "pill" : "pill-warn";

const impactPill = (v: string) =>
  v === "bullish" ? "pill-up" : v === "bearish" ? "pill-down" : "pill";

export function NewsEventsView() {
  const [events, setEvents] = useState<NewsEvent[] | null>(null);

  const load = useCallback(async () => {
    const res = await fetch(`${API_URL}/api/v1/news/events?limit=25`, { cache: "no-store" });
    if (res.ok) setEvents((await res.json()).events);
    else setEvents([]);
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 120_000);
    return () => clearInterval(id);
  }, [load]);

  if (events === null) return <div className="card h-40 animate-pulse" />;

  if (events.length === 0) {
    return (
      <p className="card p-5 text-xs text-muted">
        No clustered events yet. Events form when the news engine classifies incoming headlines and
        groups them into underlying events — currently paused because the LLM provider is out of
        credits (402). Classification resumes automatically once credits are available.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {events.map((e) => (
        <div key={e.id} className="card p-5">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`pill ${verifyPill(e.verification)}`}>{e.verification}</span>
            <span className={`pill ${impactPill(e.gold_impact)}`}>gold {e.gold_impact}</span>
            <span className="pill">{e.category}</span>
            {e.region && <span className="pill">{e.region}</span>}
            {e.importance === "high" && <span className="pill pill-gold">high importance</span>}
            <span className="num ml-auto text-[10px] text-faint">
              {e.sources_count} source{e.sources_count === 1 ? "" : "s"} · updated{" "}
              {e.last_update ? new Date(e.last_update).toISOString().slice(5, 16).replace("T", " ") : "—"} UTC
            </span>
          </div>
          <div className="mt-2.5 text-[14px] font-semibold text-ink">{e.title}</div>
          {e.articles.length > 0 && (
            <ul className="mt-2 space-y-1">
              {e.articles.slice(0, 4).map((a, i) => (
                <li key={i} className="text-[12px] leading-relaxed text-muted">
                  <span className="text-faint">[{a.source}]</span>{" "}
                  <a href={a.url} target="_blank" rel="noreferrer" className="hover:text-ink hover:underline">
                    {a.title}
                  </a>
                  {a.published_at && (
                    <span className="num text-[10px] text-faint">
                      {" "}
                      · {new Date(a.published_at).toISOString().slice(5, 16).replace("T", " ")}Z
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}
