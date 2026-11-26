import type { Metadata } from "next";
import { StrategyLabView } from "@/components/StrategyLabView";
import { PerformanceView } from "@/components/PerformanceView";

export const metadata = { title: "Strategy Lab — Aurex" };

export default function StrategiesPage() {
  return (
    <main className="page rise">
      <div className="mx-auto max-w-6xl">
        <header className="mb-5">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <h1 className="page-title">Strategy Lab</h1>
            <span className="rounded-full border border-line-subtle bg-gold-dim px-2.5 py-0.5 text-[10.5px] font-semibold uppercase tracking-wider text-gold">
              7 live strategies
            </span>
          </div>
          <p className="page-sub">
            Institutional pattern intelligence on the live gold chart — liquidity sweeps, market
            structure, order blocks and more. Pick a strategy; its signals paint directly on the
            candles.
          </p>
        </header>
        <StrategyLabView />
        <details className="card mt-5 p-5">
          <summary className="cursor-pointer text-[13px] font-semibold text-gold">
            How each strategy has actually performed
          </summary>
          <div className="mt-4">
            <PerformanceView />
          </div>
        </details>
        <footer className="mt-6 border-t border-line-subtle pt-4 text-[10.5px] leading-relaxed text-faint">
          Every signal is computed from stored candles (never lookahead) and is visible only after
          the candle closes — what you see is what was knowable at that moment.
        </footer>
      </div>
    </main>
  );
}
