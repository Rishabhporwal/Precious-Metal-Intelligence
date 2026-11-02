import { Suspense } from "react";
import Link from "next/link";
import { GoldChart } from "@/components/GoldChart";
import { LiveTicker } from "@/components/LiveTicker";
import { AnalyticsData, AnalyticsSkeleton } from "@/components/AnalyticsPanel";
import { QuantData, QuantSkeleton } from "@/components/QuantPanel";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

interface Quote {
  price: string;
  market_ts: string;
  received_at: string;
}

async function FreshnessPanel() {
  const [quote, status] = await Promise.all([
    fetch(`${API_INTERNAL_URL}/api/v1/markets/XAUUSD/quote`, {
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    })
      .then((r) => (r.ok ? (r.json() as Promise<Quote>) : null))
      .catch(() => null),
    fetch(`${API_INTERNAL_URL}/api/v1/markets`, {
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    })
      .then((r) =>
        r.ok
          ? (r.json() as Promise<{
              instruments: {
                symbol: string;
                freshness: { daily_count: number; hourly_count: number; last_daily: string | null };
              }[];
            }>)
          : null,
      )
      .catch(() => null),
  ]);

  const gold = status?.instruments.find((i) => i.symbol === "XAUUSD");
  const lastDaily = gold?.freshness.last_daily ? new Date(gold.freshness.last_daily) : null;
  const ageHours = lastDaily ? (Date.now() - lastDaily.getTime()) / 3600000 : null;
  const stale = ageHours == null || ageHours > 48;

  const rows: { label: string; value: string }[] = [
    {
      label: "Last quote received",
      value: quote?.received_at ? new Date(quote.received_at).toISOString().slice(0, 16) + "Z" : "—",
    },
    {
      label: "Quote market timestamp",
      value: quote?.market_ts ? new Date(quote.market_ts).toISOString().slice(0, 16) + "Z" : "—",
    },
    { label: "Stored daily candles", value: String(gold?.freshness.daily_count ?? 0) },
    { label: "Stored hourly candles", value: String(gold?.freshness.hourly_count ?? 0) },
  ];

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-neutral-500">
          Data freshness
        </h2>
        <span
          className={`rounded-full border px-2 py-0.5 text-[10px] ${
            stale ? "border-amber-800 text-amber-400" : "border-emerald-800 text-emerald-400"
          }`}
        >
          {stale ? "STALE — CHECK INGESTION" : "FRESH"}
        </span>
      </div>
      <dl className="mt-3 space-y-1.5 font-mono text-xs">
        {rows.map((r) => (
          <div key={r.label} className="flex justify-between gap-4">
            <dt className="text-neutral-500">{r.label}</dt>
            <dd className="text-neutral-300">{r.value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 text-[10px] leading-relaxed text-neutral-600">
        Quotes refresh every 5 min; 1-min candles every 15 min (Twelve Data free-plan credit
        budget). If freshness goes stale, check the ingestion container logs.
      </p>
    </div>
  );
}

function FreshnessSkeleton() {
  return (
    <div className="h-44 animate-pulse rounded-lg border border-neutral-800 bg-neutral-900/40" />
  );
}

export default function DashboardPage() {
  return (
    <main className="px-6 py-8 font-mono text-neutral-200">
      <div className="mx-auto max-w-4xl">
        <header className="mb-6 flex items-baseline justify-between">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-neutral-100">Dashboard</h1>
            <p className="mt-1 text-xs text-neutral-500">
              Gold focus · Phase 2 — charts from stored candles, live price over WebSocket
            </p>
          </div>
          <div className="flex gap-3 text-[11px] text-neutral-400">
            <Link href="/markets" className="underline hover:text-neutral-100">
              Markets
            </Link>
            <Link href="/status" className="underline hover:text-neutral-100">
              Service status
            </Link>
          </div>
        </header>

        <div className="space-y-4">
          <LiveTicker />
          <GoldChart initialInterval="1day" />
          <Suspense fallback={<AnalyticsSkeleton />}>
            <AnalyticsData />
          </Suspense>
          <Suspense fallback={<QuantSkeleton />}>
            <QuantData />
          </Suspense>
          <Suspense fallback={<FreshnessSkeleton />}>
            <FreshnessPanel />
          </Suspense>
        </div>

        <footer className="mt-8 border-t border-neutral-800 pt-4 text-[10px] text-neutral-600">
          All data is real market data ingested from Twelve Data — no mock data exists in this
          system. Nothing on this page is a trading recommendation.
        </footer>
      </div>
    </main>
  );
}
