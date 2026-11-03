import { VerdictRefresh } from "@/components/VerdictRefresh";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

interface Verdict {
  direction: string;
  confidence: string;
  score: number;
  price: string | number;
  narrative: string | null;
  drivers: { plain: string; vote: number; source: string }[];
  event_risk: { veto: boolean; events: { release: string; date: string }[] };
  plan: {
    entry_low: number;
    entry_high: number;
    stop: number;
    t1: number;
    t2: number;
    risk_per_oz: number;
    supports: number[];
    resistances: number[];
  } | null;
  invalidations: string[];
  key_levels: Record<string, number | null>;
  as_of: string;
}

const usd = (v: number) => `$${v.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;

function directionStyle(d: string) {
  if (d === "bullish") return { pill: "pill-up", word: "UP", color: "text-up", emoji: "📈" };
  if (d === "bearish") return { pill: "pill-down", word: "DOWN", color: "text-down", emoji: "📉" };
  return { pill: "pill-warn", word: "STAND ASIDE", color: "text-warn", emoji: "⏸️" };
}

async function getVerdict(): Promise<Verdict | null> {
  try {
    const res = await fetch(`${API_INTERNAL_URL}/api/v1/verdict/latest`, {
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    if (!res.ok) return null;
    return (await res.json()) as Verdict;
  } catch {
    return null;
  }
}

export async function VerdictCard() {
  const v = await getVerdict();

  if (!v) {
    return (
      <div className="brief-card p-6">
        <span className="pill pill-gold">Today's Verdict</span>
        <p className="plain-lead mt-3 font-medium text-ink">
          Your first daily verdict hasn't been generated yet. It combines news, economic events,
          chart patterns and trend analysis into one clear call — with exact levels.
        </p>
        <div className="mt-4">
          <VerdictRefresh />
        </div>
      </div>
    );
  }

  const s = directionStyle(v.direction);
  const hasPlan = v.plan != null;

  return (
    <div className="brief-card p-6">
      <div className="flex items-center justify-between">
        <span className="pill pill-gold">Today's Verdict</span>
        <span className="text-[11px] text-faint">
          {new Date(v.as_of).toISOString().slice(5, 16).replace("T", " ")} UTC
        </span>
      </div>

      {/* The call */}
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <span className={`text-[34px] font-semibold tracking-tight ${s.color}`}>
          {s.emoji} {v.direction === "neutral" ? "NO CLEAR TRADE" : `GOLD ${s.word}`}
        </span>
        <span className={`pill ${s.pill}`}>{v.confidence} confidence</span>
      </div>

      {v.narrative && <p className="plain-lead mt-3">{v.narrative}</p>}

      {/* The plan */}
      {hasPlan && v.plan ? (
        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[
            { label: "Get in between", value: `${usd(v.plan.entry_low)} – ${usd(v.plan.entry_high)}`, hint: "the zone where we'd enter" },
            { label: "Stop loss", value: usd(v.plan.stop), hint: "exit here if we're wrong" },
            { label: "Target 1", value: usd(v.plan.t1), hint: "first goal (1× risk)" },
            { label: "Target 2", value: usd(v.plan.t2), hint: "extended goal (2× risk)" },
          ].map((c) => (
            <div key={c.label} className="rounded-xl border border-line-subtle bg-raised p-4">
              <div className="card-title">{c.label}</div>
              <div className="num mt-1.5 text-[19px] font-medium text-ink">{c.value}</div>
              <div className="mt-1 text-[11px] text-muted">{c.hint}</div>
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-5 rounded-xl border p-4" style={{ borderColor: "rgba(180,83,9,0.25)", background: "var(--warn-dim)" }}>
          <div className="text-[13px] font-semibold text-warn">
            {v.event_risk.veto ? "Big economic news is due — smart money stands aside" : "Signals are mixed — no trade today"}
          </div>
          <p className="mt-1 text-[12.5px] leading-relaxed text-muted">
            {v.event_risk.veto
              ? `High-impact release(s) within 48h: ${v.event_risk.events.map((e) => e.release).join(", ")}. Markets can whipsaw violently on these; we resume the plan once they pass.`
              : "The signals don't agree enough to take a side. Sitting out IS the disciplined call — capital preserved is opportunity kept."}
          </p>
        </div>
      )}

      {/* Why + what would change our mind */}
      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <div>
          <div className="card-title">Why we think this</div>
          <ul className="mt-2 space-y-1.5">
            {v.drivers.map((d, i) => (
              <li key={i} className="flex gap-2 text-[12.5px] leading-relaxed text-muted">
                <span className={d.vote > 0 ? "text-up" : "text-down"}>{d.vote > 0 ? "▲" : "▼"}</span>
                {d.plain}
              </li>
            ))}
            {v.drivers.length === 0 && <li className="text-[12.5px] text-muted">No strong signals right now.</li>}
          </ul>
        </div>
        <div>
          <div className="card-title">What would change our mind</div>
          <ul className="mt-2 space-y-1.5">
            {v.invalidations.map((x, i) => (
              <li key={i} className="text-[12.5px] leading-relaxed text-muted">• {x}</li>
            ))}
          </ul>
        </div>
      </div>

      {/* Key levels */}
      {hasPlan && v.plan && (
        <div className="mt-5 flex flex-wrap gap-2">
          <span className="pill pill-up">Support {v.plan.supports.slice(0, 2).map(usd).join(" · ") || "—"}</span>
          <span className="pill pill-down">Resistance {v.plan.resistances.slice(0, 2).map(usd).join(" · ") || "—"}</span>
          <span className="pill">Risk per oz {usd(v.plan.risk_per_oz)}</span>
        </div>
      )}

      <div className="mt-4 flex items-center justify-between border-t border-line-subtle pt-3">
        <p className="text-[10.5px] leading-relaxed text-faint">
          Levels are computed from real chart data — never invented. Information, not financial advice.
        </p>
        <VerdictRefresh />
      </div>
    </div>
  );
}

export function VerdictSkeleton() {
  return <div className="brief-card h-64 animate-pulse" />;
}
