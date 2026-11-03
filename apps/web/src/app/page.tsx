import { Suspense } from "react";
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
      label: "Quote market ts",
      value: quote?.market_ts ? new Date(quote.market_ts).toISOString().slice(0, 16) + "Z" : "—",
    },
    { label: "Stored daily candles", value: String(gold?.freshness.daily_count ?? 0) },
    { label: "Stored hourly candles", value: String(gold?.freshness.hourly_count ?? 0) },
  ];

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between">
        <h2 className="card-title">Data freshness</h2>
        <span className={`pill ${stale ? "pill-warn" : "pill-up"}`}>
          <span className={`dot ${stale ? "bg-warn" : "dot-live"}`} />
          {stale ? "STALE — CHECK INGESTION" : "FRESH"}
        </span>
      </div>
      <dl className="mt-4 space-y-2">
        {rows.map((r) => (
          <div key={r.label} className="flex justify-between gap-4 text-[12.5px]">
            <dt className="text-muted">{r.label}</dt>
            <dd className="num text-ink-soft">{r.value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-4 text-[10.5px] leading-relaxed text-faint">
        Quotes refresh every 5 min; 1-min candles every 15 min (Twelve Data free-plan credit
        budget). If freshness goes stale, check the ingestion container logs.
      </p>
    </div>
  );
}

function FreshnessSkeleton() {
  return <div className="card h-44 animate-pulse" />;
}

export default function DashboardPage() {
  return (
    <main className="page rise">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="page-sub">Gold market intelligence — live price, structure, scenarios</p>
        </div>
        <div className="hidden gap-2 sm:flex">
          <span className="pill pill-gold">Gold focus</span>
          <span className="pill">Paper only · no live orders</span>
        </div>
      </header>

      <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
        <div className="min-w-0 space-y-4">
          <LiveTicker />
          <GoldChart initialInterval="1day" />
          <Suspense fallback={<AnalyticsSkeleton />}>
            <AnalyticsData />
          </Suspense>
          <Suspense fallback={<QuantSkeleton />}>
            <QuantData />
          </Suspense>
        </div>
        <div className="space-y-4">
          <Suspense fallback={<FreshnessSkeleton />}>
            <FreshnessPanel />
          </Suspense>
        </div>
      </div>

      <footer className="mt-8 border-t border-line-subtle pt-4 text-[10.5px] leading-relaxed text-faint">
        All data is real market data ingested from Twelve Data — no mock data exists in this
        system. Nothing on this page is a trading recommendation.
      </footer>
    </main>
  );
}
