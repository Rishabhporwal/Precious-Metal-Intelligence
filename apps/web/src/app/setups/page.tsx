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
    return <p className="rounded-lg border border-red-900 bg-red-950/40 p-4 text-xs text-red-300">Setups API unreachable.</p>;
  }
  const valid = res.setups.filter((s) => s.validation_status === "valid");
  const rejected = res.setups.filter((s) => s.validation_status === "rejected");

  const card = (s: Setup, rejectedVersion = false) => (
    <div key={s.id} className={`rounded-lg border bg-neutral-900/60 p-4 ${rejectedVersion ? "border-neutral-800 opacity-60" : s.direction === "long" ? "border-emerald-800" : "border-red-800"}`}>
      <div className="flex items-center justify-between">
        <span className={`text-xs font-semibold uppercase tracking-widest ${s.direction === "long" ? "text-emerald-400" : "text-red-400"}`}>
          {s.direction}
        </span>
        <span className="font-mono text-[10px] text-neutral-500">R/R {Number(s.risk_reward).toFixed(2)}</span>
      </div>
      <dl className="mt-2 space-y-1 font-mono text-[11px]">
        <div className="flex justify-between"><dt className="text-neutral-500">Entry zone</dt><dd className="text-neutral-200">{Number(s.entry_zone[0]).toFixed(2)} – {Number(s.entry_zone[1]).toFixed(2)}</dd></div>
        <div className="flex justify-between"><dt className="text-neutral-500">Stop</dt><dd className="text-red-400">{Number(s.stop).toFixed(2)}</dd></div>
        <div className="flex justify-between"><dt className="text-neutral-500">Targets</dt><dd className="text-neutral-200">{s.targets.filter(Boolean).map((t) => Number(t).toFixed(2)).join(" / ")}</dd></div>
        {s.position_size && (
          <div className="flex justify-between"><dt className="text-neutral-500">Size (1% risk)</dt><dd className="text-neutral-200">{Number(s.position_size).toFixed(3)} oz</dd></div>
        )}
      </dl>
      {rejectedVersion && s.validation_reasons.length > 0 && (
        <ul className="mt-2 list-disc pl-4 text-[10px] text-amber-400">
          {s.validation_reasons.slice(0, 3).map((r, i) => <li key={i}>{r}</li>)}
        </ul>
      )}
      <p className="mt-2 font-mono text-[9px] text-neutral-600">{s.strategy_id} · {s.anchor_time?.slice(5, 16).replace("T", " ")}Z</p>
    </div>
  );

  return (
    <>
      <section>
        <h2 className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
          Validated setups ({valid.length})
        </h2>
        {valid.length === 0 ? (
          <p className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-4 text-xs text-neutral-400">
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
          <h2 className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
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
    <main className="px-6 py-8 font-mono text-neutral-200">
      <div className="mx-auto max-w-5xl">
        <header className="mb-6">
          <h1 className="text-xl font-semibold tracking-tight text-neutral-100">Trade Setups</h1>
          <p className="mt-1 text-xs text-neutral-500">
            Phase 8 — composite candidates through the risk gate · sizing on $1,000 @ 1% risk · paper only
          </p>
        </header>
        <Suspense fallback={<div className="h-40 animate-pulse rounded-lg border border-neutral-800 bg-neutral-900/40" />}>
          <SetupsData />
        </Suspense>
        <footer className="mt-8 border-t border-neutral-800 pt-4 text-[10px] text-neutral-600">
          <a className="text-neutral-400 underline" href="/">← dashboard</a> · setups are analysis records —
          risk validation is necessary but not sufficient; final judgment is yours
        </footer>
      </div>
    </main>
  );
}
