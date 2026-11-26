import type { Metadata } from "next";
import CryptoFlowView from "@/components/CryptoFlowView";

export const metadata = { title: "Order Flow — Aurex" };

export default function CryptoPage() {
  return (
    <main className="page rise">
      <div className="mx-auto max-w-6xl">
        <header className="mb-5">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <h1 className="page-title">Order Flow</h1>
            <span className="rounded-full border border-line-subtle bg-gold-dim px-2.5 py-0.5 text-[10.5px] font-semibold uppercase tracking-wider text-gold">
              BTC · ETH · SOL
            </span>
          </div>
          <p className="page-sub">
            Who is hitting the button — aggressive buyers vs sellers inside every candle, plus open
            interest, funding and liquidations. The tape beneath the candles.
          </p>
        </header>
        <CryptoFlowView />
        <footer className="mt-6 border-t border-line-subtle pt-4 text-[10.5px] leading-relaxed text-faint">
          Per-side trade data from the OpenMarket Data API (Binance USDT-M futures), aggregated
          hourly. Information only — not financial advice.
        </footer>
      </div>
    </main>
  );
}
