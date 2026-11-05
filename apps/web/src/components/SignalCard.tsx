import { VerdictRefresh } from "@/components/VerdictRefresh";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

interface Reconciliation {
  technical?: { verdict: string; detail: string };
  fundamental?: { verdict: string; detail: string };
  market_reaction?: { verdict: string; detail: string };
  quantitative?: { verdict: string; detail: string };
  cross_market?: { nudge: number; detail: string };
}

interface Signal {
  reconciliation?: Reconciliation;
  signal_type: string;
  confidence: string;
  score: number | string;
  price: string | number;
  regime: string;
  note: string | null;
  event_veto: boolean;
  strategy_relevance: string[];
  invalidation_level: string | number | null;
  plan: { entry_low: number; entry_high: number; stop: number; t1: number; t2: number; risk_per_oz: number } | null;
  created_at: string;
  graded: boolean;
  exit_reason: string | null;
  r_multiple: string | number | null;
}

const usd = (v: number) => `$${Number(v).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;

function style(t: string) {
  if (t.includes("BUY")) return { cls: "text-up", pill: "pill-up", emoji: "🟢" };
  if (t.includes("SELL")) return { cls: "text-down", pill: "pill-down", emoji: "🔴" };
  if (t === "WAIT") return { cls: "text-warn", pill: "pill-warn", emoji: "⏸️" };
  if (t === "INVALIDATED") return { cls: "text-down", pill: "pill-down", emoji: "⛔" };
  return { cls: "text-muted", pill: "", emoji: "⏹️" };
}

const LABEL: Record<string, string> = {
  BUY: "BUY", STRONG_BUY: "STRONG BUY", SELL: "SELL", STRONG_SELL: "STRONG SELL",
  EARLY_BUY: "EARLY BUY — developing", EARLY_SELL: "EARLY SELL — developing",
  WAIT: "WAIT — setup forming", NO_TRADE: "NO TRADE", INVALIDATED: "INVALIDATED",
};

async function getSignal(): Promise<Signal | null> {
  try {
    const res = await fetch(`${API_INTERNAL_URL}/api/v1/signals/latest`, {
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    if (!res.ok) return null;
    return (await res.json()) as Signal;
  } catch {
    return null;
  }
}

/** The 9-state trading signal — decision-time record with expiry + outcome grading. */
export async function SignalCard() {
  const s = await getSignal();
  if (!s) {
    return (
      <div className="brief-card p-6">
        <span className="pill pill-gold">Trading Signal</span>
        <p className="plain-lead mt-3 font-medium text-ink">
          No signal generated yet. The signal engine fuses 33 strategies, market regime and event
          risk into one of nine states — BUY, EARLY, WAIT or NO TRADE — and every signal is
          timestamped and graded against what actually happens next.
        </p>
        <div className="mt-4">
          <VerdictRefresh />
        </div>
      </div>
    );
  }

  const st = style(s.signal_type);
  const hasPlan = s.plan != null;
  const gradedNote = s.graded
    ? `outcome graded: ${s.exit_reason ?? "—"}${s.r_multiple != null ? ` (${Number(s.r_multiple) > 0 ? "+" : ""}${Number(s.r_multiple)}R)` : ""}`
    : null;

  return (
    <div className="brief-card p-6">
      <div className="flex items-center justify-between">
        <span className="pill pill-gold">Trading Signal</span>
        <span className="num text-[11px] text-faint">
          {new Date(s.created_at).toISOString().slice(5, 16).replace("T", " ")} UTC
        </span>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <span className={`text-[32px] font-semibold tracking-tight ${st.cls}`}>
          {st.emoji} {LABEL[s.signal_type] ?? s.signal_type}
        </span>
        <span className={`pill ${st.pill}`}>{s.confidence} confidence</span>
        <span className="pill">regime: {s.regime}</span>
      </div>

      {s.note && <p className="plain-lead mt-3">{s.note}</p>}

      {/* §9: the four evidence-group verdicts, shown explicitly */}
      {s.reconciliation && (
        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          {([
            ["Technical", s.reconciliation.technical],
            ["Fundamental", s.reconciliation.fundamental],
            ["Market reaction", s.reconciliation.market_reaction],
            ["Quantitative", s.reconciliation.quantitative],
          ] as const).map(([label, grp]) => grp && (
            <div key={label} className="rounded-xl border border-line-subtle bg-raised p-4">
              <div className="flex items-center justify-between gap-2">
                <span className="card-title">{label}</span>
                <span className="pill">{grp.verdict}</span>
              </div>
              <p className="mt-1.5 text-[11.5px] leading-relaxed text-muted">{grp.detail}</p>
            </div>
          ))}
        </div>
      )}

      {hasPlan && s.plan ? (
        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[
            { label: "Get in between", value: `${usd(s.plan.entry_low)} – ${usd(s.plan.entry_high)}` },
            { label: "Stop loss", value: usd(s.plan.stop) },
            { label: "Target 1", value: usd(s.plan.t1) },
            { label: "Target 2", value: usd(s.plan.t2) },
          ].map((c) => (
            <div key={c.label} className="rounded-xl border border-line-subtle bg-raised p-4">
              <div className="card-title">{c.label}</div>
              <div className="num mt-1.5 text-[19px] font-medium text-ink">{c.value}</div>
            </div>
          ))}
        </div>
      ) : null}

      {s.strategy_relevance.length > 0 && (
        <div className="mt-5 rounded-xl border border-line-subtle bg-raised p-4">
          <div className="card-title">What matters in this regime</div>
          <ul className="mt-1.5 space-y-1">
            {s.strategy_relevance.map((r, i) => (
              <li key={i} className="text-[12.5px] text-muted">• {r}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-line-subtle pt-3">
        <p className="text-[10.5px] text-faint">
          {gradedNote ? gradedNote + " · " : ""}
          {s.invalidation_level != null
            ? `Invalidation: ${usd(Number(s.invalidation_level))} — beyond this the signal is void. `
            : ""}
          Timestamped at decision time; graded against actual outcomes. Not financial advice.
        </p>
        <VerdictRefresh />
      </div>
    </div>
  );
}

export function SignalSkeleton() {
  return <div className="brief-card h-52 animate-pulse" />;
}
