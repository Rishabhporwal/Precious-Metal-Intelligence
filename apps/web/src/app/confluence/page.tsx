import { ConfluencePanel } from "@/components/ConfluencePanel";

export const metadata = { title: "Confluence — PMI" };

const INTERVALS = ["15min", "1h", "4h", "1day"] as const;

export default function ConfluencePage() {
  return (
    <main className="page rise">
      <div className="mx-auto max-w-4xl">
        <header className="mb-5">
          <h1 className="page-title">Multi-Strategy Confluence</h1>
          <p className="page-sub">
            Where every independent strategy agrees and disagrees — deduplicated, weighted, explained.
          </p>
        </header>
        {INTERVALS.map((tf) => (
          <div key={tf} className="mb-4">
            <div className="card-title mb-2">{tf.toUpperCase()}</div>
            <ConfluencePanel interval={tf} />
          </div>
        ))}
        <footer className="mt-8 border-t border-line-subtle pt-4 text-[10.5px] leading-relaxed text-faint">
          The confluence score is transparent arithmetic over the independent verdicts — it is NOT a
          probability of success. Related strategies describing the same price move are counted once.
        </footer>
      </div>
    </main>
  );
}
