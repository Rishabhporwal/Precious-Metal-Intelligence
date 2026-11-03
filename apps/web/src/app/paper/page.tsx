import { PaperTradingView } from "@/components/PaperTradingView";

export default function PaperPage() {
  return (
    <main className="page rise">
      <div className="mx-auto max-w-5xl">
        <header className="mb-6">
          <h1 className="page-title">Paper Trading</h1>
          <p className="mt-1 text-xs text-muted">
            SIMULATED only — fills at stored quotes, stops filled pessimistically. No live orders ever.
          </p>
        </header>
        <PaperTradingView />
        <footer className="mt-8 border-t border-line-subtle pt-4 text-[10.5px] text-faint">
          <a className="text-muted underline" href="/">← dashboard</a> ·
          SL/TP monitored by the scheduler every 2 min; stop fills assume the worse of stop/quote
        </footer>
      </div>
    </main>
  );
}
