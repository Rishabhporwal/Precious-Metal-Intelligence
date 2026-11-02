import { PaperTradingView } from "@/components/PaperTradingView";

export default function PaperPage() {
  return (
    <main className="px-6 py-8 font-mono text-neutral-200">
      <div className="mx-auto max-w-5xl">
        <header className="mb-6">
          <h1 className="text-xl font-semibold tracking-tight text-neutral-100">Paper Trading</h1>
          <p className="mt-1 text-xs text-neutral-500">
            SIMULATED only — fills at stored quotes, stops filled pessimistically. No live orders ever.
          </p>
        </header>
        <PaperTradingView />
        <footer className="mt-8 border-t border-neutral-800 pt-4 text-[10px] text-neutral-600">
          <a className="text-neutral-400 underline" href="/">← dashboard</a> ·
          SL/TP monitored by the scheduler every 2 min; stop fills assume the worse of stop/quote
        </footer>
      </div>
    </main>
  );
}
