import { AlertsView } from "@/components/AlertsView";

export default function AlertsPage() {
  return (
    <main className="page rise">
      <div className="mx-auto max-w-5xl">
        <header className="mb-6">
          <h1 className="page-title">Alerts</h1>
          <p className="mt-1 text-xs text-muted">
            Phase 8 — price/structure/setup alerts · cooldown + dedupe built in · Telegram when configured
          </p>
        </header>
        <AlertsView />
        <footer className="mt-8 border-t border-line-subtle pt-4 text-[10.5px] text-faint">
          <a className="text-muted underline" href="/">← dashboard</a> ·
          a continuously-true condition fires once per cooldown window, never repeatedly
        </footer>
      </div>
    </main>
  );
}
