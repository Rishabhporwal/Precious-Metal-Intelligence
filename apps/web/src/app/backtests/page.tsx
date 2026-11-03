import { BacktestsView } from "@/components/BacktestsView";

export default function BacktestsPage() {
  return (
    <main className="page rise">
      <div className="mx-auto max-w-5xl">
        <header className="mb-6">
          <h1 className="page-title">Backtesting</h1>
          <p className="mt-1 text-xs text-muted">
            Phase 9 — leakage-gated replay · pessimistic intrabar assumptions · costs deducted · IS/OOS split
          </p>
        </header>
        <BacktestsView />
        <footer className="mt-8 border-t border-line pt-4 text-[10px] leading-relaxed text-faint">
          <a className="text-muted underline" href="/">← dashboard</a> ·
          Results are model-based estimates with stated assumptions — not achievable-performance
          claims. Future-dependent detections are excluded by the leakage gate and counted.
        </footer>
      </div>
    </main>
  );
}
