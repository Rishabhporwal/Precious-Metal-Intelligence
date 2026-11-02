import { AlertsView } from "@/components/AlertsView";

export default function AlertsPage() {
  return (
    <main className="px-6 py-8 font-mono text-neutral-200">
      <div className="mx-auto max-w-5xl">
        <header className="mb-6">
          <h1 className="text-xl font-semibold tracking-tight text-neutral-100">Alerts</h1>
          <p className="mt-1 text-xs text-neutral-500">
            Phase 8 — price/structure/setup alerts · cooldown + dedupe built in · Telegram when configured
          </p>
        </header>
        <AlertsView />
        <footer className="mt-8 border-t border-neutral-800 pt-4 text-[10px] text-neutral-600">
          <a className="text-neutral-400 underline" href="/">← dashboard</a> ·
          a continuously-true condition fires once per cooldown window, never repeatedly
        </footer>
      </div>
    </main>
  );
}
