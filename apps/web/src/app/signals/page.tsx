import { SignalLogView } from "@/components/SignalLogView";

export const metadata = { title: "Signal Log — PMI" };

export default function SignalsPage() {
  return (
    <main className="page rise">
      <div className="mx-auto max-w-5xl">
        <header className="mb-5">
          <h1 className="page-title">Signal Log</h1>
          <p className="page-sub">
            Every signal, timestamped at decision time and graded against what actually happened.
          </p>
        </header>
        <SignalLogView />
        <footer className="mt-8 border-t border-line-subtle pt-4 text-[10.5px] leading-relaxed text-faint">
          Evaluation rules (§14): a system that avoids false signals by never generating them is not
          good; one that generates many without risk-adjusted performance is worse. Out-of-sample
          columns are kept separate from in-sample everywhere in this platform.
        </footer>
      </div>
    </main>
  );
}
