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
  bullish: "text-up border-up/30",
  neutral: "text-warn border-warn/30",
  bearish: "text-down border-down/30",
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
      <p className="card p-5 border-[rgba(246,70,93,0.3)] bg-[var(--down-dim)] text-xs text-down">
        Analyst API unreachable.
      </p>
    );
  }
  if (res.status === "none") {
    return (
      <div className="card p-5 text-xs text-muted">
        No analysis yet. Click <span className="text-ink-soft">Generate fresh analysis</span> —
        the graph gathers all deterministic evidence first, then calls the LLM once (cached).
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="card p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span
            className={`rounded px-2 py-0.5 text-[10px] ${
              res.status === "llm"
                ? "bg-violet-900/60 text-violet-300"
                : "bg-white/[0.06] text-muted"
            }`}
          >
            {res.status === "llm" ? `LLM: ${res.model}` : "DETERMINISTIC FALLBACK"}
          </span>
          <span className="num text-[10px] text-faint">
            prompt {res.prompt_version} · {res.generated_at?.slice(0, 16).replace("T", " ")}Z
            {res.cache_hit ? " · cache hit" : ""}
          </span>
        </div>
        <p className="mt-3 text-sm leading-relaxed text-ink-soft">{res.summary}</p>
        {res.data_warnings.length > 0 && (
          <ul className="mt-2 list-disc pl-4 text-[10px] text-warn">
            {res.data_warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        )}
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {res.scenarios.map((s, i) => (
          <div key={i} className={`rounded-lg border bg-white/[0.02] p-4 ${DIR_COLOR[s.direction] ?? "border-line"}`}>
            <div className={`text-xs font-semibold uppercase tracking-widest ${DIR_COLOR[s.direction]?.split(" ")[1] ?? ""}`}>
              {s.direction}
            </div>
            <p className="mt-2 text-[11px] leading-relaxed text-ink-soft">{s.narrative}</p>
            {s.supporting.length > 0 && (
              <p className="mt-2 text-[10px] text-up/80">+ {s.supporting.join(", ")}</p>
            )}
            {s.conflicting.length > 0 && (
              <p className="mt-1 text-[10px] text-down/80">− {s.conflicting.join(", ")}</p>
            )}
            <div className="mt-3 space-y-1 border-t border-line pt-2 text-[10px] text-muted">
              <p><span className="text-muted">Confirm:</span> {s.confirmation}</p>
              <p><span className="text-muted">Invalidate:</span> {s.invalidation}</p>
            </div>
          </div>
        ))}
      </div>

      {"risk" in res && res.risk != null && (
        <div className="card p-5">
          <h3 className="card-title text-muted">
            Risk constraints (deterministic Python — Phase 8 builds on these)
          </h3>
          <dl className="mt-2 grid grid-cols-2 gap-2 num text-[11px] md:grid-cols-4">
            {Object.entries(res.risk)
              .filter(([, v]) => typeof v === "number")
              .map(([k, v]) => (
                <div key={k}>
                  <dt className="text-faint">{k}</dt>
                  <dd className="text-ink-soft">{String(v)}</dd>
                </div>
              ))}
          </dl>
          {typeof res.risk.event_risk_warning === "string" && (
            <p className="mt-2 text-[10px] text-warn">{res.risk.event_risk_warning}</p>
          )}
        </div>
      )}
    </div>
  );
}

function AnalystSkeleton() {
  return <div className="h-64 animate-pulse card animate-pulse opacity-60" />;
}

export default function AnalystPage() {
  return (
    <main className="page rise">
      <div className="mx-auto max-w-5xl">
        <header className="mb-6 flex items-baseline justify-between">
          <div>
            <h1 className="page-title">AI Market Analyst</h1>
            <p className="mt-1 text-xs text-muted">
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
        <footer className="mt-8 border-t border-line pt-4 text-[10px] leading-relaxed text-faint">
          <a className="text-muted underline" href="/">← dashboard</a> ·
          Every numeric level in the narrative is validated against the evidence pack; violations
          trigger one retry, then a deterministic fallback. Not financial advice.
        </footer>
      </div>
    </main>
  );
}
