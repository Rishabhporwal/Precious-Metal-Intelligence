import { ChartWorkspace } from "@/components/ChartWorkspace";

export const metadata = { title: "Chart Workspace — PMI" };

export default function ChartPage() {
  return (
    <main className="page rise">
      <header className="mb-5 flex items-end justify-between">
        <div>
          <h1 className="page-title">Chart Workspace</h1>
          <p className="page-sub">
            Every strategy, on the chart — enable layers, inspect signals, read each verdict.
          </p>
        </div>
        <span className="pill pill-gold hidden sm:inline-flex">Master chart</span>
      </header>
      <ChartWorkspace />
      <footer className="mt-8 border-t border-line-subtle pt-4 text-[10.5px] leading-relaxed text-faint">
        All markers map to persisted detection records — nothing is drawn that the engine didn't
        detect. Historical signals stay anchored at their original detection time (no repainting).
      </footer>
    </main>
  );
}
