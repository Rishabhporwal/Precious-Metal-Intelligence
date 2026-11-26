"use client";

import { useEffect, useRef, useState } from "react";
import { Vela } from "@luxalgo/vela";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const SYMBOLS = ["BTC", "ETH", "SOL"] as const;

interface SymbolRow {
  symbol: string;
  has_data: boolean;
  price?: string;
  as_of?: string | null;
  buy_share_24h?: number | null;
  buy_volume_24h?: number;
  sell_volume_24h?: number;
  change_pct?: number | null;
  open_interest?: string | null;
  funding_rate?: string | null;
  liq_1h?: { buy: string | null; sell: string | null } | null;
}

interface Candle {
  market_ts: string;
  open: string;
  high: string;
  low: string;
  close: string;
  buy_volume: string | null;
  sell_volume: string | null;
}

function theme() {
  const css = getComputedStyle(document.documentElement);
  const v = (n: string, fb: string) => css.getPropertyValue(n).trim() || fb;
  const dark = document.documentElement.classList.contains("dark");
  return {
    background: v("--bg-elev", dark ? "#141821" : "#ffffff"),
    textColor: v("--chart-text", "#6d7480"),
    gridColor: v("--chart-grid", "rgba(20,30,50,0.06)"),
    borderColor: v("--line", "rgba(20,30,50,0.1)"),
    upColor: v("--chart-up", "#059669"),
    downColor: v("--chart-down", "#e11d48"),
    fontFamily: "ui-monospace, SFMono-Regular, monospace",
  };
}

function CryptoChart({ symbol }: { symbol: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let dead = false;
    const chart = new Vela(el, {
      symbol: `${symbol}USDT`,
      timeframe: "60",
      theme: theme() as never,
      bars: 120,
    });
    chart.drawings.showToolbar(false);
    chart.data.registerProvider("pmi-crypto", {
      async getBars(ticker: string, timeframe: string, range?: { from?: number; limit?: number }) {
        const interval = timeframe === "60" ? "1h" : timeframe === "1D" ? "1day" : "1h";
        const res = await fetch(`${API_URL}/api/v1/crypto/candles?symbol=${symbol}&limit=200`);
        if (!res.ok) return [];
        const d = (await res.json()) as { candles: Candle[] };
        const bars = d.candles
          .map((c) => ({
            time: new Date(c.market_ts).getTime(),
            open: Number(c.open), high: Number(c.high),
            low: Number(c.low), close: Number(c.close),
          }))
          .filter((b) => Number.isFinite(b.time) && (!range?.from || b.time >= range.from))
          .sort((a, b) => a.time - b.time);
        return ticker.endsWith("USDT") ? bars : [];
      },
      async listSymbols() {
        return SYMBOLS.map((s) => ({ ticker: `${s}USDT`, description: `${s} perpetual` }));
      },
    });
    chart.ready().catch(() => undefined);
    return () => {
      dead = true;
      try {
        (chart as unknown as { destroy?: () => void }).destroy?.();
      } catch {
        try {
          (chart as unknown as { remove?: () => void }).remove?.();
        } catch {
          /* noop */
        }
      }
    };
  }, [symbol]);
  return <div ref={ref} className="h-[380px] w-full" />;
}

const compact = (v: number) =>
  v >= 1e9 ? `${(v / 1e9).toFixed(2)}B` : v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `${(v / 1e3).toFixed(1)}K` : v.toFixed(0);

export default function CryptoFlowView() {
  const [rows, setRows] = useState<SymbolRow[]>([]);
  const [sel, setSel] = useState<string>("BTC");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    const load = () =>
      fetch(`${API_URL}/api/v1/crypto/overview`)
        .then((r) => r.json())
        .then((d) => alive && setRows(d.symbols ?? []))
        .catch(() => undefined)
        .finally(() => alive && setLoading(false));
    load();
    const t = setInterval(load, 60_000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  const bysym = Object.fromEntries(rows.map((r) => [r.symbol, r])) as Record<string, SymbolRow | undefined>;

  return (
    <div>
      {/* symbol selector + pressure cards */}
      <div className="grid gap-3 sm:grid-cols-3">
        {SYMBOLS.map((sym) => {
          const r = bysym[sym];
          const share = r?.buy_share_24h;
          const active = sel === sym;
          return (
            <button
              key={sym}
              onClick={() => setSel(sym)}
              className={`card p-4 text-left transition-all ${active ? "ring-2 ring-gold/60" : "card-hover"}`}
            >
              <div className="flex items-center justify-between">
                <span className="num text-[15px] font-bold text-ink">{sym}</span>
                {r?.has_data ? (
                  <span className={`num text-[13px] font-semibold ${(r.change_pct ?? 0) >= 0 ? "text-up" : "text-down"}`}>
                    {(r.change_pct ?? 0) >= 0 ? "+" : ""}
                    {r.change_pct?.toFixed(2)}%
                  </span>
                ) : (
                  <span className="text-[10.5px] text-faint">no data yet</span>
                )}
              </div>
              <div className="num mt-1 text-[19px] font-bold text-ink">
                {r?.has_data ? `$${Number(r.price).toLocaleString("en-US", { maximumFractionDigits: 2 })}` : "—"}
              </div>
              <div className="mt-3">
                <div className="flex justify-between text-[10px] uppercase tracking-wider text-faint">
                  <span>Sellers</span>
                  <span>Buyers</span>
                </div>
                <div className="mt-1 flex h-2 overflow-hidden rounded-full bg-down/25">
                  <div
                    className="bg-up/80"
                    style={{ width: `${share != null ? Math.round(share * 100) : 50}%` }}
                  />
                </div>
                <div className="num mt-1 flex justify-between text-[10.5px] text-muted">
                  <span>{share != null ? `${Math.round((1 - share) * 100)}% sold` : "—"}</span>
                  <span>{share != null ? `${Math.round(share * 100)}% bought` : "—"}</span>
                </div>
              </div>
              <div className="mt-3 grid grid-cols-3 gap-2 border-t border-line-subtle pt-2.5 text-[10.5px]">
                <div>
                  <div className="text-faint">Open int.</div>
                  <div className="num text-ink">{r?.open_interest ? compact(Number(r.open_interest)) : "—"}</div>
                </div>
                <div>
                  <div className="text-faint">Funding</div>
                  <div className={`num ${Number(r?.funding_rate) >= 0 ? "text-up" : "text-down"}`}>
                    {r?.funding_rate ? `${(Number(r.funding_rate) * 100).toFixed(3)}%` : "—"}
                  </div>
                </div>
                <div>
                  <div className="text-faint">Liq 1h</div>
                  <div className="num text-ink">
                    {r?.liq_1h
                      ? compact(Number(r.liq_1h.buy ?? 0) + Number(r.liq_1h.sell ?? 0))
                      : "—"}
                  </div>
                </div>
              </div>
            </button>
          );
        })}
      </div>

      {/* chart */}
      <div className="card mt-4 overflow-hidden">
        <div className="flex items-center justify-between border-b border-line-subtle px-4 py-2.5">
          <div className="flex items-center gap-2">
            <span className="num text-[13px] font-bold text-ink">{sel}/USDT</span>
            <span className="rounded bg-black/[0.04] px-1.5 py-0.5 text-[9.5px] font-semibold uppercase tracking-wider text-faint dark:bg-white/[0.06]">
              perp · 1h
            </span>
            <span className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-up">
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-up opacity-60" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-up" />
              </span>
              order flow
            </span>
          </div>
          <span className="text-[10.5px] text-faint">
            green candles = buyers in control · red = sellers
          </span>
        </div>
        <CryptoChart symbol={sel} />
      </div>

      {loading && <p className="mt-3 text-[12px] text-muted">Loading order flow…</p>}
      {!loading && rows.length && rows.every((r) => !r.has_data) && (
        <div className="card mt-4 p-4 text-[12.5px] text-muted">
          No crypto data yet. The ingestion needs <span className="num">OPENMARKET_API_KEY</span> in
          the .env — add your free key from openmarket.xyz account settings, then wait one cycle
          (about 15 minutes).
        </div>
      )}
    </div>
  );
}
