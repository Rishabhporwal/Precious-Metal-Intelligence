export const metadata = { title: "Learn — PMI" };

const TERMS: { term: string; plain: string; deeper: string }[] = [
  {
    term: "Spot price",
    plain: "The current price for gold delivered right now — the number you see quoted.",
    deeper: "XAU/USD is the international spot price of gold quoted in US dollars per troy ounce.",
  },
  {
    term: "Trend",
    plain: "The general direction prices have been moving — up, down, or sideways.",
    deeper:
      "We measure it with moving-average alignment and ADX (a trend-strength score from 0–100). Above ~25 usually means a real trend, below ~20 usually means choppy.",
  },
  {
    term: "Support & resistance",
    plain: "Price levels where gold has repeatedly stopped falling (support) or stopped rising (resistance).",
    deeper:
      "We detect them from swing points — places where price turned around — confirmed by how many touches occurred.",
  },
  {
    term: "Liquidity sweep",
    plain: "A quick dip below an obvious level that triggers stop-loss orders, then price snaps back. Big players use these orders to fill large positions.",
    deeper:
      "Our detector requires the level to be broken, then reclaimed by a candle close back inside within N bars — anchored at the reclaim bar so the signal never repaints.",
  },
  {
    term: "Fair Value Gap (FVG)",
    plain: "A 'hole' in the chart where price moved so fast it skipped levels. Price often comes back to fill it.",
    deeper: "A three-candle pattern where the middle candle's range leaves an uncovered gap between candle 1's high and candle 3's low.",
  },
  {
    term: "Break of Structure (BOS)",
    plain: "Price pushing through a previous turning point — a sign the trend is continuing.",
    deeper: "Confirmed only on candle close beyond the prior swing point; intrabar breaks don't count.",
  },
  {
    term: "Volatility",
    plain: "How much gold is jumping around. High volatility = bigger moves, bigger risk.",
    deeper: "We track historical volatility (annualized standard deviation) and its percentile versus the past year.",
  },
  {
    term: "Real yield",
    plain: "What US bonds pay after inflation. When real yields fall, gold tends to shine — gold pays no interest, so the opportunity cost drops.",
    deeper: "We track the 10-year TIPS yield (FRED: DFII10) and its rolling correlation with gold.",
  },
  {
    term: "R:R (risk/reward)",
    plain: "How much you stand to make versus what you risk. 2:1 means targeting twice what you're risking.",
    deeper: "Our risk engine rejects setups below 1.5:1 and sizes positions so a stop-out costs 1% of account equity.",
  },
  {
    term: "Paper trading",
    plain: "Practicing with pretend money. Same prices, same mechanics — zero real risk.",
    deeper: "Our simulator fills orders at stored quotes and assumes the worse outcome when a candle touches both your stop and target.",
  },
];

export default function LearnPage() {
  return (
    <main className="page rise">
      <div className="mx-auto max-w-3xl">
        <header className="mb-6">
          <h1 className="page-title">Learn the basics</h1>
          <p className="page-sub">
            The words you'll see around the app — explained without jargon.
          </p>
        </header>

        <div className="space-y-3">
          {TERMS.map((t) => (
            <div key={t.term} className="card p-5">
              <div className="text-[14px] font-semibold text-ink">{t.term}</div>
              <p className="plain-lead mt-1.5 text-[13.5px]">{t.plain}</p>
              <details className="mt-2">
                <summary className="cursor-pointer text-[12px] font-medium text-gold select-none">
                  Want the technical detail?
                </summary>
                <p className="mt-1.5 text-[12px] leading-relaxed text-muted">{t.deeper}</p>
              </details>
            </div>
          ))}
        </div>

        <footer className="mt-8 border-t border-line-subtle pt-4 text-[10.5px] leading-relaxed text-faint">
          Education only — nothing here is financial advice.
        </footer>
      </div>
    </main>
  );
}
