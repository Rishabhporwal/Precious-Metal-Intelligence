import { Suspense } from "react";

interface InstrumentRow {
  symbol: string;
  name: string;
  asset_class: string;
  enabled: boolean;
  entitlement_verified: boolean;
  verification_note: string | null;
  provider_symbol: string | null;
  provider_name: string | null;
  freshness: {
    last_daily: string | null;
    last_hourly: string | null;
    daily_count: number;
    hourly_count: number;
  };
}

interface Candle {
  market_ts: string;
  close: string;
}

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

async function getJson<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_INTERNAL_URL}${path}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

function Sparkline({ candles, color }: { candles: Candle[]; color: string }) {
  const closes = candles.map((c) => Number(c.close)).filter((n) => Number.isFinite(n));
  if (closes.length < 2) return null;
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const range = max - min || 1;
  const W = 260;
  const H = 56;
  const pts = closes
    .map((v, i) => {
      const x = (i / (closes.length - 1)) * W;
      const y = H - ((v - min) / range) * (H - 6) - 3;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="mt-3 h-14 w-full" preserveAspectRatio="none">
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" />
    </svg>
  );
}

function fmt(v: string | null | undefined, digits = 2): string {
  if (v == null) return "—";
  const n = Number(v);
  return Number.isFinite(n)
    ? n.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits })
    : "—";
}

function ago(iso: string | null | undefined): string {
  if (!iso) return "never";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 90) return `${Math.round(s)}s ago`;
  if (s < 5400) return `${Math.round(s / 60)}m ago`;
  if (s < 172800) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

async function MarketsData() {
  const [instrumentsResp, xauQuote, xagQuote, xauCandles, xagCandles] = await Promise.all([
    getJson<{ instruments: InstrumentRow[] }>("/api/v1/markets"),
    getJson<{ price: string; market_ts: string }>("/api/v1/markets/XAUUSD/quote"),
    getJson<{ price: string; market_ts: string }>("/api/v1/markets/XAGUSD/quote"),
    getJson<{ candles: Candle[] }>("/api/v1/markets/XAUUSD/candles?interval=1day&limit=90"),
    getJson<{ candles: Candle[] }>("/api/v1/markets/XAGUSD/candles?interval=1day&limit=90"),
  ]);

  if (!instrumentsResp) {
    return (
      <p className="rounded-lg border border-red-900 bg-red-950/40 p-4 text-sm text-red-300">
        Market API unreachable — check that the api and quant services are healthy.
      </p>
    );
  }

  const instruments = instrumentsResp.instruments;
  const enabled = instruments.filter((i) => i.enabled);
  const pending = instruments.filter((i) => !i.enabled);

  return (
    <>
      <section className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {[
          { name: "Gold — XAU/USD (spot)", quote: xauQuote, candles: xauCandles?.candles ?? [], color: "#f5c451" },
          {
            name: "Silver — COMEX SI (futures)",
            quote: xagQuote,
            candles: xagCandles?.candles ?? [],
            color: "#a8b6c8",
          },
        ].map((card) => (
          <div key={card.name} className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-4">
            <div className="text-xs text-neutral-400">{card.name}</div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="text-3xl font-semibold text-neutral-100">{fmt(card.quote?.price)}</span>
              <span className="text-[11px] text-neutral-500">{ago(card.quote?.market_ts)}</span>
            </div>
            <Sparkline candles={card.candles} color={card.color} />
            <div className="mt-1 text-[10px] text-neutral-600">
              last {card.candles.length} daily closes · source: Twelve Data via quant engine
            </div>
          </div>
        ))}
      </section>

      <section className="mt-6">
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-widest text-neutral-500">
          Ingested instruments
        </h2>
        <div className="overflow-x-auto rounded-lg border border-neutral-800">
          <table className="w-full text-left text-xs">
            <thead className="bg-neutral-900 text-neutral-500">
              <tr>
                {["Symbol", "Provider symbol", "Daily", "Hourly", "Last daily", "Note"].map((h) => (
                  <th key={h} className="px-3 py-2 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {enabled.map((i) => (
                <tr key={i.symbol} className="border-t border-neutral-800">
                  <td className="px-3 py-2 font-medium text-neutral-200">{i.symbol}</td>
                  <td className="px-3 py-2 text-neutral-400">{i.provider_symbol}</td>
                  <td className="px-3 py-2 text-neutral-300">{i.freshness.daily_count}</td>
                  <td className="px-3 py-2 text-neutral-300">{i.freshness.hourly_count}</td>
                  <td className="px-3 py-2 text-neutral-400">{ago(i.freshness.last_daily)}</td>
                  <td className="px-3 py-2 text-neutral-500">{i.verification_note ?? ""}</td>
                </tr>
              ))}
              {pending.map((i) => (
                <tr key={i.symbol} className="border-t border-neutral-800 opacity-50">
                  <td className="px-3 py-2 font-medium text-neutral-400">{i.symbol}</td>
                  <td className="px-3 py-2 text-neutral-500">not verified</td>
                  <td className="px-3 py-2">—</td>
                  <td className="px-3 py-2">—</td>
                  <td className="px-3 py-2">—</td>
                  <td className="px-3 py-2 text-neutral-500">provider entitlement not confirmed</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

function MarketsSkeleton() {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="h-32 animate-pulse rounded-lg border border-neutral-800 bg-neutral-900/40" />
        <div className="h-32 animate-pulse rounded-lg border border-neutral-800 bg-neutral-900/40" />
      </div>
      <div className="h-40 animate-pulse rounded-lg border border-neutral-800 bg-neutral-900/40" />
    </div>
  );
}

export default function MarketsPage() {
  return (
    <main className="min-h-screen bg-neutral-950 px-6 py-10 font-mono text-neutral-200">
      <div className="mx-auto max-w-3xl">
        <header className="mb-8">
          <h1 className="text-xl font-semibold tracking-tight text-neutral-100">Markets</h1>
          <p className="mt-1 text-xs text-neutral-500">
            Phase 1 — live Twelve Data ingestion · real market data only, nothing mocked
          </p>
        </header>
        <Suspense fallback={<MarketsSkeleton />}>
          <MarketsData />
        </Suspense>
        <footer className="mt-8 border-t border-neutral-800 pt-4 text-[11px] text-neutral-600">
          <a className="text-neutral-400 underline" href="/">
            ← service status
          </a>
        </footer>
      </div>
    </main>
  );
}
