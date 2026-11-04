import { Suspense } from "react";
import Link from "next/link";
import { LiveTicker } from "@/components/LiveTicker";
import { VerdictCard, VerdictSkeleton } from "@/components/VerdictCard";
import { SignalCard } from "@/components/SignalCard";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

interface Quote {
  price: string;
}

interface Candle {
  market_ts: string;
  close: string;
}

interface Structure {
  trend: string;
  prev_day: { high: number | null; low: number | null };
}

interface Analysis {
  status: string;
  summary: string | null;
  generated_at: string | null;
}

async function getJson<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_INTERNAL_URL}${path}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

function trendWord(trend: string): string {
  if (trend === "up") return "rising";
  if (trend === "down") return "falling";
  return "moving sideways";
}

function trendLabel(trend: string): string {
  if (trend === "up") return "Uptrend";
  if (trend === "down") return "Downtrend";
  return "Sideways";
}

async function Brief() {
  const [quote, candles, struct, analysis] = await Promise.all([
    getJson<Quote>("/api/v1/markets/XAUUSD/quote"),
    getJson<{ candles: Candle[] }>("/api/v1/markets/XAUUSD/candles?interval=1day&limit=30"),
    getJson<Structure>("/api/v1/markets/XAUUSD/structure?interval=1h"),
    getJson<Analysis>("/api/v1/analysis/latest/XAUUSD"),
  ]);

  const price = quote?.price ? Number(quote.price) : null;
  const closes = (candles?.candles ?? []).map((c) => Number(c.close)).filter(Number.isFinite);
  const prevClose = closes.length >= 2 ? closes[closes.length - 2] : null;
  const changePct = price != null && prevClose ? ((price - prevClose) / prevClose) * 100 : null;
  const weekAgo = closes.length >= 6 ? closes[closes.length - 6] : null;
  const changeWeekPct = price != null && weekAgo ? ((price - weekAgo) / weekAgo) * 100 : null;

  const dayWord =
    changePct == null ? "—" : changePct >= 0.05 ? "up" : changePct <= -0.05 ? "down" : "little changed";
  const trend = struct?.trend ?? "neutral";

  // Plain-English headline — deterministic from real data, no invented facts.
  const headline =
    price != null
      ? `Gold is ${dayWord} around $${price.toLocaleString("en-US", { maximumFractionDigits: 0 })} and ${trendWord(trend)} on short-term charts.`
      : "Live gold price is unavailable right now — data connection is being checked.";

  const happenings: { icon: string; title: string; detail: string; tone: string }[] = [];
  if (changePct != null) {
    happenings.push({
      icon: changePct >= 0 ? "📈" : "📉",
      title: changePct >= 0 ? "Gold moved up today" : "Gold moved down today",
      detail: `${changePct >= 0 ? "+" : ""}${changePct.toFixed(2)}% versus yesterday's close${changeWeekPct != null ? ` · ${changeWeekPct >= 0 ? "+" : ""}${changeWeekPct.toFixed(1)}% this week` : ""}.`,
      tone: changePct >= 0 ? "text-up" : "text-down",
    });
  }
  happenings.push({
    icon: "🧭",
    title: `Short-term picture: ${trendLabel(trend)}`,
    detail:
      trend === "up"
        ? "Buyers have been in control on the hourly chart — pullbacks have been bought."
        : trend === "down"
          ? "Sellers have been in control on the hourly chart — rallies have been sold."
          : "Price is range-bound; neither side is in control right now.",
    tone: "",
  });
  if (struct?.prev_day.high != null && struct?.prev_day.low != null) {
    happenings.push({
      icon: "📌",
      title: "Yesterday's boundaries",
      detail: `Gold traded between $${struct.prev_day.low.toLocaleString("en-US", { maximumFractionDigits: 0 })} and $${struct.prev_day.high.toLocaleString("en-US", { maximumFractionDigits: 0 })}. These are the levels traders watch for breakouts.`,
      tone: "",
    });
  }

  return (
    <div className="space-y-4">
      {/* THE CALL — trading signal first, verdict evidence below */}
      <SignalCard />
      <VerdictCard />

      {/* Market context below */}
      <div className="flex items-center gap-2 px-1">
        <span className="card-title">Market context</span>
      </div>
      <div className="brief-card p-6">
        <div className="flex items-center gap-2">
          <span className="pill">Market brief</span>
          {analysis?.generated_at && (
            <span className="text-[11px] text-faint">
              analysis from {analysis.generated_at.slice(5, 16).replace("T", " ")} UTC
            </span>
          )}
        </div>
        <p className="plain-lead mt-3 font-medium text-ink">{headline}</p>

        {/* What happened — 3 plain cards */}
        <div className="mt-5 grid gap-3 sm:grid-cols-3">
          {happenings.slice(0, 3).map((h, i) => (
            <div key={i} className="rounded-xl border border-line-subtle bg-raised p-4">
              <div className="text-[20px] leading-none">{h.icon}</div>
              <div className={`mt-2 text-[13px] font-semibold ${h.tone || "text-ink"}`}>{h.title}</div>
              <div className="mt-1 text-[12px] leading-relaxed text-muted">{h.detail}</div>
            </div>
          ))}
        </div>

        {/* AI take in plain words */}
        {analysis?.summary && !analysis.summary.startsWith("Deterministic fallback") && (
          <div className="mt-5 rounded-xl border p-4" style={{ borderColor: "rgba(199,143,10,0.25)", background: "var(--gold-dim)" }}>
            <div className="card-title" style={{ color: "var(--gold-bright)" }}>
              What our analysts are watching
            </div>
            <p className="mt-2 text-[13px] leading-relaxed text-ink-soft">{analysis.summary}</p>
            <Link href="/analyst" className="mt-2 inline-block text-[12px] font-medium text-gold hover:underline">
              See the full analysis →
            </Link>
          </div>
        )}

        <p className="mt-4 text-[10.5px] leading-relaxed text-faint">
          This brief is generated from real market data and our own analysis. It is information, not
          financial advice — never trade more than you can afford to lose.
        </p>
      </div>

      {/* Live price */}
      <LiveTicker />
    </div>
  );
}

function BriefSkeleton() {
  return <div className="brief-card h-72 animate-pulse" />;
}

function QuickActions() {
  const actions = [
    {
      href: "/paper",
      title: "Practice with pretend money",
      detail: "Try out ideas risk-free in your practice portfolio.",
      emoji: "🧪",
    },
    {
      href: "/alerts",
      title: "Get notified",
      detail: "Ping me when gold crosses a price I care about.",
      emoji: "🔔",
    },
    {
      href: "/learn",
      title: "Learn the basics",
      detail: "Gold-market words explained in plain English.",
      emoji: "🎓",
    },
  ];
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {actions.map((a) => (
        <Link key={a.href} href={a.href} className="card card-hover block p-5">
          <div className="text-[22px] leading-none">{a.emoji}</div>
          <div className="mt-2.5 text-[13.5px] font-semibold text-ink">{a.title}</div>
          <div className="mt-1 text-[12px] leading-relaxed text-muted">{a.detail}</div>
        </Link>
      ))}
    </div>
  );
}

export default function HomePage() {
  return (
    <main className="page rise">
      <div className="mx-auto max-w-5xl">
        <header className="mb-6">
          <h1 className="page-title">Good day 👋</h1>
          <p className="page-sub">Here's what gold is doing — in plain English.</p>
        </header>

        <Suspense fallback={<VerdictSkeleton />}>
          <Brief />
        </Suspense>

        <div className="section-gap" />
        <QuickActions />

        <footer className="mt-8 border-t border-line-subtle pt-4 text-[10.5px] leading-relaxed text-faint">
          All data comes from real market feeds — no simulated prices anywhere. Practice trading uses
          pretend money only. PMI is not a broker and never places live orders.
        </footer>
      </div>
    </main>
  );
}
