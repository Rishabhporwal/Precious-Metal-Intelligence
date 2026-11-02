import { BacktestsView } from "@/components/BacktestsView";

export default function BacktestsPage() {
  return (
    <main className="px-6 py-8 font-mono text-neutral-200">
      <div className="mx-auto max-w-5xl">
        <header className="mb-6">
          <h1 className="text-xl font-semibold tracking-tight text-neutral-100">Backtesting</h1>
          <p className="mt-1 text-xs text-neutral-500">
            Phase 9 — leakage-gated replay · pessimistic intrabar assumptions · costs deducted · IS/OOS split
          </p>
        </header>
        <BacktestsView />
        <footer className="mt-8 border-t border-neutral-800 pt-4 text-[10px] leading-relaxed text-neutral-600">
          <a className="text-neutral-400 underline" href="/">← dashboard</a> ·
          Results are model-based estimates with stated assumptions — not achievable-performance
          claims. Future-dependent detections are excluded by the leakage gate and counted.
        </footer>
      </div>
    </main>
  );
}
