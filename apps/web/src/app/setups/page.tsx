import { Suspense } from "react";
import { GenerateAnalysisButton } from "@/components/GenerateAnalysisButton";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

interface Setup {
  id: number;
  strategy_id: string;
  direction: string;
  entry_zone: string[];
  stop: string;
  targets: (string | null)[];
  risk_reward: string;
  position_size: string | null;
  validation_status: string;
  validation_reasons: string[];
  anchor_time: string | null;
}

async function SetupsData() {
  const res = await fetch(`${API_INTERNAL_URL}/api/v1/setups`, {
    cache: "no-store",
    signal: AbortSignal.timeout(15000),
  })
    .then((r) => (r.ok ? (r.json() as Promise<{ setups: Setup[]; count: number }>) : null))
    .catch(() => null);

  if (!res) {
    return <p className="card p-5 border-[rgba(246,70,93,0.3)] bg-[var(--down-dim)] text-xs text-down">Setups API unreachable.</p>;
  }
  const valid = res.setups.filter((s) => s.validation_status === "valid");
  const rejected = res.setups.filter((s) => s.validation_status === "rejected");

  const card = (s: Setup, rejectedVersion = false) => (
    <div key={s.id} className={`rounded-lg border bg-white/[0.02] p-4 ${rejectedVersion ? "border-line opacity-60" : s.direction === "long" ? "border-up/30" : "border-down/30"}`}>
      <div className="flex items-center justify-between">
        <span className={`text-xs font-semibold uppercase tracking-widest ${s.direction === "long" ? "text-up" : "text-down"}`}>
          {s.direction}
        </span>
        <span className="num text-[10px] text-muted">R/R {Number(s.risk_reward).toFixed(2)}</span>
      </div>
      <dl className="mt-2 space-y-1 num text-[11px]">
        <div className="flex justify-between"><dt className="text-muted">Entry zone</dt><dd className="text-ink-soft">{Number(s.entry_zone[0]).toFixed(2)} – {Number(s.entry_zone[1]).toFixed(2)}</dd></div>
        <div className="flex justify-between"><dt className="text-muted">Stop</dt><dd className="text-down">{Number(s.stop).toFixed(2)}</dd></div>
        <div className="flex justify-between"><dt className="text-muted">Targets</dt><dd className="text-ink-soft">{s.targets.filter(Boolean).map((t) => Number(t).toFixed(2)).join(" / ")}</dd></div>
        {s.position_size && (
          <div className="flex justify-between"><dt className="text-muted">Size (1% risk)</dt><dd className="text-ink-soft">{Number(s.position_size).toFixed(3)} oz</dd></div>
        )}
      </dl>
      {rejectedVersion && s.validation_reasons.length > 0 && (
        <ul className="mt-2 list-disc pl-4 text-[10px] text-warn">
          {s.validation_reasons.slice(0, 3).map((r, i) => <li key={i}>{r}</li>)}
        </ul>
      )}
      <p className="mt-2 num text-[10px] text-faint">{s.strategy_id} · {s.anchor_time?.slice(5, 16).replace("T", " ")}Z</p>
    </div>
  );

  return (
    <>
      <section>
        <h2 className="mb-2 card-title text-muted">
          Validated setups ({valid.length})
        </h2>
        {valid.length === 0 ? (
          <p className="card p-5 text-xs text-muted">
            No validated setups right now. The composite strategy only validates when sweep → MSS →
            displacement → FVG → OB all align AND the risk gates pass (fresh quote, stop distance,
            R/R ≥ 1.5, no 48h event risk).
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">{valid.map((s) => card(s))}</div>
        )}
      </section>

      {rejected.length > 0 && (
        <section className="mt-6">
          <h2 className="mb-2 card-title text-muted">
            Rejected by the risk gate ({rejected.length}) — shown for transparency
          </h2>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">{rejected.slice(0, 6).map((s) => card(s, true))}</div>
        </section>
      )}
    </>
  );
}

export default function SetupsPage() {
  return (
    <main className="page rise">
      <div className="mx-auto max-w-5xl">
        <header className="mb-6">
          <h1 className="page-title">Trade Setups</h1>
          <p className="mt-1 text-xs text-muted">
            Idea cards from our engine — every one checked against the risk rules first
          </p>
        </header>
        <Suspense fallback={<div className="h-40 animate-pulse card animate-pulse opacity-60" />}>
          <SetupsData />
        </Suspense>
        <footer className="mt-8 border-t border-line-subtle pt-4 text-[10.5px] text-faint">
          <a className="text-muted underline" href="/">← dashboard</a> · setups are analysis records —
          risk validation is necessary but not sufficient; final judgment is yours
        </footer>
      </div>
    </main>
  );
}
