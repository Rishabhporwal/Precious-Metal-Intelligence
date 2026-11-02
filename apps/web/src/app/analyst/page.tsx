import { Suspense } from "react";
import { GenerateAnalysisButton } from "@/components/GenerateAnalysisButton";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

interface Scenario {
  direction: string;
  narrative: string;
  supporting: string[];
  conflicting: string[];
  confirmation: string;
  invalidation: string;
}

interface Analysis {
  id?: number;
  status: string;
  model: string | null;
  prompt_version: string;
  summary: string;
  scenarios: Scenario[];
  risk: Record<string, unknown>;
  data_warnings: string[];
  cache_hit: boolean;
  generated_at: string | null;
  evidence_hash?: string;
  already_existed?: boolean;
}

const DIR_COLOR: Record<string, string> = {
  bullish: "text-emerald-400 border-emerald-800",
  neutral: "text-amber-400 border-amber-800",
  bearish: "text-red-400 border-red-800",
};

async function AnalystData() {
  const res = await fetch(`${API_INTERNAL_URL}/api/v1/analysis/latest/XAUUSD`, {
    cache: "no-store",
    signal: AbortSignal.timeout(20000),
  })
    .then((r) => (r.ok ? (r.json() as Promise<Analysis>) : ({ status: "none" } as Analysis)))
    .catch(() => null);

  if (!res) {
    return (
      <p className="rounded-lg border border-red-900 bg-red-950/40 p-4 text-xs text-red-300">
        Analyst API unreachable.
      </p>
    );
  }
  if (res.status === "none") {
    return (
      <div className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-4 text-xs text-neutral-400">
        No analysis yet. Click <span className="text-neutral-200">Generate fresh analysis</span> —
        the graph gathers all deterministic evidence first, then calls the LLM once (cached).
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span
            className={`rounded px-2 py-0.5 text-[10px] ${
              res.status === "llm"
                ? "bg-violet-900/60 text-violet-300"
                : "bg-neutral-800 text-neutral-400"
            }`}
          >
            {res.status === "llm" ? `LLM: ${res.model}` : "DETERMINISTIC FALLBACK"}
          </span>
          <span className="font-mono text-[10px] text-neutral-600">
            prompt {res.prompt_version} · {res.generated_at?.slice(0, 16).replace("T", " ")}Z
            {res.cache_hit ? " · cache hit" : ""}
          </span>
        </div>
        <p className="mt-3 text-sm leading-relaxed text-neutral-200">{res.summary}</p>
        {res.data_warnings.length > 0 && (
          <ul className="mt-2 list-disc pl-4 text-[10px] text-amber-400">
            {res.data_warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        )}
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {res.scenarios.map((s, i) => (
          <div key={i} className={`rounded-lg border bg-neutral-900/60 p-4 ${DIR_COLOR[s.direction] ?? "border-neutral-800"}`}>
            <div className={`text-xs font-semibold uppercase tracking-widest ${DIR_COLOR[s.direction]?.split(" ")[1] ?? ""}`}>
              {s.direction}
            </div>
            <p className="mt-2 text-[11px] leading-relaxed text-neutral-300">{s.narrative}</p>
            {s.supporting.length > 0 && (
              <p className="mt-2 text-[10px] text-emerald-500/80">+ {s.supporting.join(", ")}</p>
            )}
            {s.conflicting.length > 0 && (
              <p className="mt-1 text-[10px] text-red-500/80">− {s.conflicting.join(", ")}</p>
            )}
            <div className="mt-3 space-y-1 border-t border-neutral-800 pt-2 text-[10px] text-neutral-500">
              <p><span className="text-neutral-400">Confirm:</span> {s.confirmation}</p>
              <p><span className="text-neutral-400">Invalidate:</span> {s.invalidation}</p>
            </div>
          </div>
        ))}
      </div>

      {"risk" in res && res.risk != null && (
        <div className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-4">
          <h3 className="text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
            Risk constraints (deterministic Python — Phase 8 builds on these)
          </h3>
          <dl className="mt-2 grid grid-cols-2 gap-2 font-mono text-[11px] md:grid-cols-4">
            {Object.entries(res.risk)
              .filter(([, v]) => typeof v === "number")
              .map(([k, v]) => (
                <div key={k}>
                  <dt className="text-neutral-600">{k}</dt>
                  <dd className="text-neutral-300">{String(v)}</dd>
                </div>
              ))}
          </dl>
          {typeof res.risk.event_risk_warning === "string" && (
            <p className="mt-2 text-[10px] text-amber-400">{res.risk.event_risk_warning}</p>
          )}
        </div>
      )}
    </div>
  );
}

function AnalystSkeleton() {
  return <div className="h-64 animate-pulse rounded-lg border border-neutral-800 bg-neutral-900/40" />;
}

export default function AnalystPage() {
  return (
    <main className="px-6 py-8 font-mono text-neutral-200">
      <div className="mx-auto max-w-5xl">
        <header className="mb-6 flex items-baseline justify-between">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-neutral-100">AI Market Analyst</h1>
            <p className="mt-1 text-xs text-neutral-500">
              Phase 7 — LangGraph evidence synthesis · LLM narrates, Python computes every number
            </p>
          </div>
        </header>
        <div className="mb-4">
          <GenerateAnalysisButton />
        </div>
        <Suspense fallback={<AnalystSkeleton />}>
          <AnalystData />
        </Suspense>
        <footer className="mt-8 border-t border-neutral-800 pt-4 text-[10px] leading-relaxed text-neutral-600">
          <a className="text-neutral-400 underline" href="/">← dashboard</a> ·
          Every numeric level in the narrative is validated against the evidence pack; violations
          trigger one retry, then a deterministic fallback. Not financial advice.
        </footer>
      </div>
    </main>
  );
}
