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
  const [instrumentsResp, xauQuote, xauCandles] = await Promise.all([
    getJson<{ instruments: InstrumentRow[] }>("/api/v1/markets"),
    getJson<{ price: string; market_ts: string }>("/api/v1/markets/XAUUSD/quote"),
    getJson<{ candles: Candle[] }>("/api/v1/markets/XAUUSD/candles?interval=1day&limit=90"),
  ]);

  if (!instrumentsResp) {
    return (
      <p className="card p-5 border-[rgba(246,70,93,0.3)] bg-[var(--down-dim)] text-sm text-down">
        Market API unreachable — check that the api and quant services are healthy.
      </p>
    );
  }

  const instruments = instrumentsResp.instruments;
  const enabled = instruments.filter((i) => i.enabled);
  const parked = instruments.filter((i) => !i.enabled);

  return (
    <>
      <section>
        <div className="rounded-lg border border-line bg-white/[0.02] p-5">
          <div className="text-xs text-muted">Gold — XAU/USD (spot)</div>
          <div className="mt-1 flex items-baseline gap-3">
            <span className="text-5xl font-semibold text-ink">{fmt(xauQuote?.price)}</span>
            <span className="text-[11px] text-muted">{ago(xauQuote?.market_ts)}</span>
          </div>
          <Sparkline candles={xauCandles?.candles ?? []} color="#f5c451" />
          <div className="mt-1 text-[10px] text-faint">
            last {xauCandles?.candles.length ?? 0} daily closes · source: Twelve Data via quant engine
          </div>
        </div>
      </section>

      <section className="mt-6">
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-widest text-muted">
          Instrument registry
        </h2>
        <div className="overflow-x-auto card">
          <table className="w-full text-left text-xs">
            <thead className="bg-white/[0.02] text-muted">
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
                <tr key={i.symbol} className="border-t border-line">
                  <td className="px-3 py-2 font-medium text-ink-soft">{i.symbol}</td>
                  <td className="px-3 py-2 text-muted">{i.provider_symbol}</td>
                  <td className="px-3 py-2 text-ink-soft">{i.freshness.daily_count}</td>
                  <td className="px-3 py-2 text-ink-soft">{i.freshness.hourly_count}</td>
                  <td className="px-3 py-2 text-muted">{ago(i.freshness.last_daily)}</td>
                  <td className="px-3 py-2 text-muted">{i.verification_note ?? ""}</td>
                </tr>
              ))}
              {parked.map((i) => (
                <tr key={i.symbol} className="border-t border-line opacity-50">
                  <td className="px-3 py-2 font-medium text-muted">{i.symbol}</td>
                  <td className="px-3 py-2 text-muted">
                    {i.provider_symbol ?? "not verified"}
                  </td>
                  <td className="px-3 py-2">{i.freshness.daily_count}</td>
                  <td className="px-3 py-2">{i.freshness.hourly_count}</td>
                  <td className="px-3 py-2">{i.freshness.last_daily ? ago(i.freshness.last_daily) : "—"}</td>
                  <td className="px-3 py-2 text-muted">{i.verification_note ?? "provider entitlement not confirmed"}</td>
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
        <div className="h-32 animate-pulse card animate-pulse opacity-60" />
        <div className="h-32 animate-pulse card animate-pulse opacity-60" />
      </div>
      <div className="h-40 animate-pulse card animate-pulse opacity-60" />
    </div>
  );
}

export default function MarketsPage() {
  return (
    <main className="page rise">
      <div className="mx-auto max-w-3xl">
        <header className="mb-8">
          <h1 className="page-title">Markets</h1>
          <p className="mt-1 text-xs text-muted">
            Phase 1 — live Twelve Data ingestion · real market data only, nothing mocked
          </p>
        </header>
        <Suspense fallback={<MarketsSkeleton />}>
          <MarketsData />
        </Suspense>
        <footer className="mt-8 border-t border-line pt-4 text-[11px] text-faint">
          <a className="text-muted underline" href="/status">
            ← service status
          </a>
        </footer>
      </div>
    </main>
  );
}
