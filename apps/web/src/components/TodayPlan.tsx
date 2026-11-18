import { LiveTicker } from "@/components/LiveTicker";
import { fmtUaeDate, fmtUaeTime } from "@/lib/time";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

interface VerdictPlan {
  entry_low?: number;
  entry_high?: number;
  stop?: number;
  t1?: number;
  t2?: number;
  risk_per_oz?: number;
  atr14?: number;
  scalp?: {
    entry_low?: number;
    entry_high?: number;
    stop?: number;
    t1?: number;
    t2?: number;
    risk_per_oz?: number;
  };
}

interface EvidenceSplit {
  bullish_points?: number;
  bearish_points?: number;
  bullish_pct?: number | null;
  bearish_pct?: number | null;
  components?: { label: string; points: number; direction: string }[];
}

interface VerdictDriver {
  source?: string;
  label?: string;
  plain?: string;
}

interface Verdict {
  direction: string;
  confidence: string;
  score?: number;
  evidence_split?: EvidenceSplit;
  drivers?: VerdictDriver[];
  as_of: string;
  plan?: VerdictPlan;
  key_levels?: { supports?: number[]; resistances?: number[]; prev_day_low?: number; prev_day_high?: number };
  trend_daily?: { trend?: string };
  trend_hourly?: { trend?: string };
  event_risk?: { veto?: boolean; events?: { release: string; date: string }[] };
  narrative?: string | null;
}

interface Signal {
  signal_type: string;
  created_at: string;
  reconciliation?: {
    fundamental?: { detail?: string };
    market_reaction?: { counts?: Record<string, number> };
  };
}

interface NewsArticle {
  title: string;
  sentiment: string | null;
  driver?: string | null;
  published_at: string;
}

const DRIVER_LABEL: Record<string, string> = {
  rates: "Interest rates & the Fed",
  usd: "The US dollar",
  geopolitics: "Wars & world tensions",
  physical: "Physical demand & supply",
  positioning: "Big-trader positioning",
  market: "Overall market mood",
  other: "Other factors",
};

const usd = (n: number) => `$${n.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;

async function getJson<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_INTERNAL_URL}${path}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

// --- plain-language mapping: no state codes, no scores, no jargon ---

function callSentence(verdict: Verdict | null, signal: Signal | null): {
  headline: string;
  trade: string | null;
  tone: "down" | "up" | "wait";
} {
  const d = (verdict?.direction ?? "").toLowerCase();
  const st = signal?.signal_type ?? "";
  const confirmed = st.startsWith("STRONG") || st === "BUY" || st === "SELL";
  if (d.includes("bear") || d.includes("down")) {
    return {
      headline: confirmed
        ? "Gold is likely to fall. The signs line up."
        : "Gold is more likely to fall than rise right now.",
      trade: "Consider selling (short) — details below.",
      tone: "down",
    };
  }
  if (d.includes("bull") || d.includes("up")) {
    return {
      headline: confirmed
        ? "Gold is likely to rise. The signs line up."
        : "Gold is more likely to rise than fall right now.",
      trade: "Consider buying (long) — details below.",
      tone: "up",
    };
  }
  return {
    headline: "No clear direction today — the honest answer is to wait.",
    trade: null,
    tone: "wait",
  };
}

function confidenceWord(c: string): string {
  if (c === "high") return "We're fairly confident.";
  if (c === "medium") return "We're somewhat confident.";
  return "We're NOT confident — treat this with extra care.";
}

function whyBullets(verdict: Verdict, signal: Signal | null, news: NewsArticle[] | null): string[] {
  const out: string[] = [];
  for (const d of verdict.drivers ?? []) {
    if (d.source === "physical" && d.plain) out.push(d.plain);
  }
  const dt = (verdict.trend_daily?.trend ?? "").toLowerCase();
  const ht = (verdict.trend_hourly?.trend ?? "").toLowerCase();
  if (dt === "down" || ht === "down")
    out.push("The price has been falling — sellers have been in control on the charts.");
  else if (dt === "up" || ht === "up")
    out.push("The price has been rising — buyers have been in control on the charts.");

  // news, in plain words — with the DRIVER mix (rates vs war vs dollar etc.)
  const recent = (news ?? []).filter(
    (a) => a.sentiment === "bullish" || a.sentiment === "bearish",
  );
  if (recent.length) {
    const byDriver = new Map<string, { bull: number; bear: number }>();
    for (const a of recent) {
      const d = a.driver && DRIVER_LABEL[a.driver] ? a.driver : "other";
      const slot = byDriver.get(d) ?? { bull: 0, bear: 0 };
      if (a.sentiment === "bullish") slot.bull += 1;
      else slot.bear += 1;
      byDriver.set(d, slot);
    }
    const ranked = [...byDriver.entries()].sort(
      (x, y) => Math.abs(y[1].bear - y[1].bull) - Math.abs(x[1].bear - x[1].bull),
    );
    for (const [driver, { bull, bear }] of ranked.slice(0, 3)) {
      const lean = bear > bull ? "pulling gold down" : bull > bear ? "pushing gold up" : "balanced";
      out.push(`${DRIVER_LABEL[driver]}: ${bear} negative vs ${bull} positive headlines — ${lean}.`);
    }
  }

  // event risk, in plain words
  const ev = verdict.event_risk;
  if (ev?.veto && ev.events?.length) {
    out.push(
      `Big economic news is coming (${ev.events[0].release.split("(")[0].trim()} on ${ev.events[0].date}) — gold can move sharply. Waiting is often smarter until it passes.`,
    );
  }

  // reaction, in plain words
  const counts = signal?.reconciliation?.market_reaction?.counts;
  if (counts) {
    const c = (counts.confirms ?? 0) + (counts.contradicts ?? 0);
    if (c >= 3) {
      out.push(
        `When similar news hit before, gold moved as our models expected ${Math.max(counts.confirms ?? 0, counts.contradicts ?? 0)} out of ${c} times — a decent, not perfect, track record.`,
      );
    }
  }
  if (out.length === 0) out.push("The usual signals are quiet — there isn't much pushing gold right now.");
  return out.slice(0, 4);
}

// Targets come from the 1-hour chart, so they are SHORT-TERM. Estimate how fast
// the first goal is typically reached from recent volatility: distance ÷ ATR(1h).
function horizonLabel(plan: VerdictPlan): string | null {
  if (plan.t1 == null || plan.atr14 == null || plan.atr14 <= 0) return null;
  const entry = plan.entry_low != null && plan.entry_high != null
    ? (plan.entry_low + plan.entry_high) / 2
    : plan.stop;
  if (entry == null) return null;
  const bars = Math.abs(plan.t1 - entry) / plan.atr14;
  const hours = bars * 1; // signals run on the 1h chart
  if (hours <= 12) return "intraday — the first goal is often reached within hours";
  if (hours <= 36) return "short-term — the first goal is often reached within about a day";
  if (hours <= 96) return "short-term — the first goal is typically 1–3 days away";
  return "short swing — expect several days for the first goal";
}

function PlanRow({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-line-subtle py-2.5 last:border-0">
      <span className="text-[12.5px] text-muted">{label}</span>
      <span className={`num text-[15px] font-semibold ${tone ?? "text-ink"}`}>{value}</span>
    </div>
  );
}

export async function TodayPlan() {
  const [verdict, signal, quote, news] = await Promise.all([
    getJson<Verdict>("/api/v1/verdict/latest?symbol=XAUUSD"),
    getJson<Signal>("/api/v1/signals/latest?symbol=XAUUSD&interval=1h"),
    getJson<{ price: string }>("/api/v1/markets/XAUUSD/quote"),
    getJson<{ articles?: NewsArticle[] }>("/api/v1/macro/news?limit=30"),
  ]);

  const { headline, trade, tone } = callSentence(verdict, signal);
  const price = quote?.price ? Number(quote.price) : null;
  const plan = verdict?.plan ?? {};
  const hasPlan = plan.stop != null && (plan.entry_low != null || plan.t1 != null);
  const supports = verdict?.key_levels?.supports ?? [];
  const resistances = verdict?.key_levels?.resistances ?? [];
  const why = verdict ? whyBullets(verdict, signal, news?.articles ?? null) : [];

  return (
    <div className="space-y-4">
      <div className="card card-accent p-6 sm:p-8">
        {/* THE HEADLINE */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="pill">Today&apos;s call</span>
          <span className="text-[11px] font-medium text-muted">
            {fmtUaeDate()} · UAE time
          </span>
          <span className="text-[11px] text-faint">
            {verdict?.as_of ? `updated ${fmtUaeTime(verdict.as_of)} UAE` : ""}
          </span>
          {price != null && (
            <span className="ml-auto num text-[13px] font-semibold text-ink">
              Gold now: {usd(price)}
            </span>
          )}
        </div>

        <h2 className="mt-4 text-[22px] font-semibold leading-snug text-ink sm:text-[26px]">
          {headline}
        </h2>
        {verdict && (
          <p className="mt-1.5 text-[12.5px] text-muted">
            {confidenceWord(verdict.confidence)}
            {trade ? ` ${trade}` : ""}
          </p>
        )}

        {/* THE TRADE PLAN — only when we actually have one */}
        {hasPlan ? (
          <div className="mt-6 rounded-xl border border-line-subtle bg-raised p-4 sm:p-5">
            <div className="card-title">If you swing trade (hold 1–3 days), here&apos;s the plan</div>
            <div className="mt-2">
              <PlanRow
                label="Get in around"
                value={
                  plan.entry_low != null && plan.entry_high != null && plan.entry_low !== plan.entry_high
                    ? `${usd(plan.entry_low)} – ${usd(plan.entry_high)}`
                    : usd((plan.entry_low ?? plan.t1) as number)
                }
              />
              <PlanRow
                label="Give up if it hits (stop loss)"
                value={usd(plan.stop as number)}
                tone="text-down"
              />
              <PlanRow
                label="First goal (take profit 1)"
                value={plan.t1 != null ? usd(plan.t1) : "—"}
                tone="text-up"
              />
              <PlanRow
                label="Bigger goal (take profit 2)"
                value={plan.t2 != null ? usd(plan.t2) : "—"}
                tone="text-up"
              />
            </div>
            {horizonLabel(plan) && (
              <p className="mt-2.5 text-[11.5px] leading-relaxed text-muted">
                <span className="font-semibold text-ink">Time horizon:</span>{" "}
                {horizonLabel(plan)} (based on how fast gold has been moving lately).
              </p>
            )}
          </div>
        ) : null}

        {hasPlan && plan.scalp?.stop != null && plan.scalp.t1 != null && (
          <div className="mt-3 rounded-xl border border-line-subtle bg-raised p-4 sm:p-5">
            <div className="card-title">If you scalp (tighter, faster — same direction)</div>
            <div className="mt-2">
              <PlanRow
                label="Get in around"
                value={
                  plan.scalp.entry_low != null && plan.scalp.entry_high != null
                    ? `${usd(plan.scalp.entry_low)} – ${usd(plan.scalp.entry_high)}`
                    : "—"
                }
              />
              <PlanRow
                label="Give up if it hits (stop loss)"
                value={usd(plan.scalp.stop)}
                tone="text-down"
              />
              <PlanRow label="First goal (1R)" value={plan.scalp.t1 != null ? usd(plan.scalp.t1) : "—"} tone="text-up" />
              <PlanRow label="Bigger goal (2R)" value={plan.scalp.t2 != null ? usd(plan.scalp.t2) : "—"} tone="text-up" />
            </div>
            <p className="mt-2.5 text-[11.5px] leading-relaxed text-muted">
              <span className="font-semibold text-ink">Scalp risk:</span> ~
              {usd(plan.scalp.risk_per_oz ?? 0)}/oz — at the 1% rule that&apos;s roughly{" "}
              <span className="num font-semibold text-ink">
                {(10 / Math.max(1, plan.scalp.risk_per_oz ?? 1)).toFixed(2)} oz
              </span>{" "}
              with a $1,000 account. Exits are quick: this trade should resolve in hours, not days.
            </p>
          </div>
        )}

        {!hasPlan && (
          <div className="mt-6 rounded-xl border border-line-subtle bg-raised p-4 sm:p-5">
            <div className="card-title">No trade recommended right now</div>
            <p className="mt-1.5 text-[12.5px] leading-relaxed text-muted">
              The signs don&apos;t point clearly in either direction. Staying out <em>is</em> the
              disciplined move. When a clear trade appears, it will show up here — with an entry
              price, stop loss and targets — and in your morning Telegram message.
            </p>
          </div>
        )}

        {/* SUPPORT / RESISTANCE — one line each, plain */}
        {(supports.length > 0 || resistances.length > 0) && (
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {resistances.length > 0 && (
              <div className="rounded-xl border border-line-subtle bg-raised p-4">
                <div className="text-[12px] text-muted">If gold rises, expect sellers near</div>
                <div className="num mt-1 text-[16px] font-semibold text-down">
                  {usd(resistances[0])}
                </div>
                <div className="mt-0.5 text-[11px] text-faint">resistance</div>
              </div>
            )}
            {supports.length > 0 && (
              <div className="rounded-xl border border-line-subtle bg-raised p-4">
                <div className="text-[12px] text-muted">If gold falls, expect buyers near</div>
                <div className="num mt-1 text-[16px] font-semibold text-up">
                  {usd(supports[0])}
                </div>
                <div className="mt-0.5 text-[11px] text-faint">support</div>
              </div>
            )}
          </div>
        )}

        {/* WHY — plain English, expandable */}
        <details className="mt-5 rounded-xl border border-line-subtle bg-raised p-4">
          <summary className="cursor-pointer text-[13px] font-semibold text-gold">
            Why? See the reasons and the confidence breakdown
          </summary>
          {verdict?.evidence_split && verdict.evidence_split.bullish_pct != null && (
            <div className="mt-3">
              <div className="text-[12px] text-muted">
                Of the weighted evidence that voted,{" "}
                <span className={`num font-bold ${verdict.evidence_split.bearish_pct! > verdict.evidence_split.bullish_pct! ? "text-down" : "text-up"}`}>
                  {verdict.evidence_split.bearish_pct! >= verdict.evidence_split.bullish_pct! ? verdict.evidence_split.bearish_pct : verdict.evidence_split.bullish_pct}%
                </span>{" "}
                points {verdict.evidence_split.bearish_pct! >= verdict.evidence_split.bullish_pct! ? "bearish (fall)" : "bullish (rise)"}:
              </div>
              <div className="mt-2 flex h-2.5 w-full overflow-hidden rounded-full bg-line-subtle">
                <div
                  className="h-full bg-[var(--up,#10b981)]"
                  style={{ width: `${verdict.evidence_split.bullish_pct ?? 0}%` }}
                />
                <div
                  className="h-full bg-[var(--down,#f6465d)]"
                  style={{ width: `${verdict.evidence_split.bearish_pct ?? 0}%` }}
                />
              </div>
              <div className="mt-2 space-y-1">
                {(verdict.evidence_split.components ?? []).map((c, i) => (
                  <div key={i} className="flex items-baseline justify-between gap-3 text-[11.5px]">
                    <span className="text-muted">{c.label}</span>
                    <span
                      className={`num font-semibold ${
                        c.direction === "bullish" ? "text-up" : c.direction === "bearish" ? "text-down" : "text-faint"
                      }`}
                    >
                      {c.points > 0 ? "+" : ""}{c.points.toFixed(1)}
                    </span>
                  </div>
                ))}
              </div>
              <p className="mt-2 text-[10px] leading-relaxed text-faint">
                Percent = share of weighted evidence (vote-share), not a probability of success.
                Each point: daily trend ±2.0, hourly ±1.0, pattern signals ±1.0, news ±0.5.
              </p>
            </div>
          )}
          <ul className="mt-3 space-y-2">
            {why.map((w, i) => (
              <li key={i} className="flex gap-2 text-[12.5px] leading-relaxed text-muted">
                <span className="text-gold">•</span>
                <span>{w}</span>
              </li>
            ))}
          </ul>
        </details>

        <p className="mt-4 text-[10.5px] leading-relaxed text-faint">
          Built from real market data. Information only — not financial advice. Never trade more
          than you can afford to lose.
        </p>
      </div>

      <LiveTicker />
    </div>
  );
}

export function TodayPlanSkeleton() {
  return <div className="card h-96 animate-pulse" />;
}
