import { Suspense } from "react";
import { getServiceRows, type ServiceRow } from "@/lib/serviceStatus";

const STATE_STYLES: Record<ServiceRow["status"], { dot: string; text: string; label: string }> = {
  ok: { dot: "bg-up", text: "text-up", label: "OK" },
  degraded: { dot: "bg-warn", text: "text-warn", label: "DEGRADED" },
  down: { dot: "bg-down", text: "text-down", label: "DOWN" },
};

function ServiceCard({ row }: { row: ServiceRow }) {
  const s = STATE_STYLES[row.status];
  return (
    <div className="card p-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`inline-block h-2 w-2 rounded-full ${s.dot}`} />
          <span className="text-sm font-medium text-ink">{row.label}</span>
        </div>
        <span className={`text-[11px] font-semibold tracking-widest ${s.text}`}>{s.label}</span>
      </div>
      <div className="mt-2 flex items-center justify-between text-xs text-muted">
        <span>:{row.port}</span>
        <span>{row.version ?? "—"}</span>
      </div>
      <p className="mt-2 text-xs text-muted">{row.detail}</p>
      {row.deps.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {row.deps.map((d) => (
            <span
              key={d.name}
              className={`rounded-full border px-2 py-0.5 text-[10px] ${
                d.state === "up"
                  ? "pill pill-up"
                  : d.state === "unconfigured"
                    ? "border-line text-muted"
                    : "border-down/30 text-down"
              }`}
            >
              {d.name}
              {d.state === "up" && d.latencyMs !== undefined ? ` · ${d.latencyMs}ms` : ` · ${d.state}`}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

async function StatusSection() {
  const rows = await getServiceRows();
  const allOk = rows.every((r) => r.status === "ok");
  return (
    <>
      <div
        className={`mb-5 inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs ${
          allOk ? "pill pill-up" : "pill pill-warn"
        }`}
      >
        <span
          className={`inline-block h-1.5 w-1.5 rounded-full ${
            allOk ? "bg-up" : "bg-warn"
          }`}
        />
        {allOk ? "ALL SYSTEMS OPERATIONAL" : "STACK PARTIALLY UP"}
      </div>
      <section className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {rows.map((row) => (
          <ServiceCard key={row.id} row={row} />
        ))}
      </section>
    </>
  );
}

function StatusSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {Array.from({ length: 5 }).map((_, i) => (
        <div
          key={i}
          className="h-28 animate-pulse card animate-pulse opacity-60"
        />
      ))}
    </div>
  );
}

export default function Home() {
  return (
    <main className="page rise">
      <div className="mx-auto max-w-3xl">
        <header className="mb-8">
          <h1 className="page-title">
            Precious Metals Intelligence
          </h1>
          <p className="mt-1 text-xs text-muted">
            Service status · live probes, refreshed per request
          </p>
        </header>

        <Suspense fallback={<StatusSkeleton />}>
          <StatusSection />
        </Suspense>

        <footer className="mt-8 border-t border-line pt-4 text-[11px] leading-relaxed text-faint">
          <p>
            <a className="text-muted underline" href="/markets">
              Markets →
            </a>{" "}
            live ingested market data
          </p>
          <p className="mt-1">
            Market data: real Twelve Data ingestion (Phase 1) — no mock data exists in this system.
          </p>
          <p className="mt-1">
            Health JSON:{" "}
            <a className="text-muted underline" href="/api/health">
              /api/health
            </a>{" "}
            ·{" "}
            <a className="text-muted underline" href="http://localhost:8000/readyz">
              api :8000/readyz
            </a>{" "}
            ·{" "}
            <a className="text-muted underline" href="http://localhost:8001/ready">
              quant :8001/ready
            </a>
          </p>
        </footer>
      </div>
    </main>
  );
}
