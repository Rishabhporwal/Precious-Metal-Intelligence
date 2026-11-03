import { PerformanceView } from "@/components/PerformanceView";

export const metadata = { title: "Strategy Performance — PMI" };

export default function PerformancePage() {
  return (
    <main className="page rise">
      <header className="mb-5">
        <h1 className="page-title">Strategy Performance</h1>
        <p className="page-sub">
          How each strategy has actually performed — backtested with honest assumptions, compared side by side.
        </p>
      </header>
      <PerformanceView />
      <footer className="mt-8 border-t border-line-subtle pt-4 text-[10.5px] leading-relaxed text-faint">
        Backtested results are model-based estimates with stated assumptions — they are not
        achievable-performance claims. In-sample (IS) and out-of-sample (OOS) numbers are shown
        separately so in-sample results can't masquerade as validated ones.
      </footer>
    </main>
  );
}
