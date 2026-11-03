import { Suspense } from "react";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

interface MacroSeries {
  series_id: string;
  title: string | null;
  units: string | null;
  as_of_date: string | null;
  value: string | null;
  previous_value: string | null;
  change: number | null;
  fetched_at: string | null;
}

interface CftcRow {
  series_id: string;
  title: string | null;
  as_of_date: string | null;
  net_noncomm: string | null;
  details: Record<string, number | null>;
}

interface MacroSummary {
  series: MacroSeries[];
  cftc: CftcRow[];
  provider_health: { fred: { credentials_configured: boolean }; cftc: { credentials_configured: boolean } };
}

interface EventRow {
  release_name: string;
  event_date: string | null;
  actual_value: string | null;
}

interface NewsArticle {
  source: string;
  url: string;
  title: string;
  summary: string | null;
  published_at: string | null;
  classified: boolean;
  sentiment: string | null;
}

const SERIES_LABELS: Record<string, string> = {
  DGS2: "2Y Treasury yield",
  DGS10: "10Y Treasury yield",
  DFII10: "10Y real yield",
  DTWEXBGS: "Broad USD index (DXY proxy)",
  CPIAUCSL: "CPI",
  PCEPI: "PCE index",
  PAYEMS: "Nonfarm payrolls",
  UNRATE: "Unemployment rate",
  DCOILWTICO: "WTI crude (spot)",
};

async function MacroData() {
  const [summary, events, news] = await Promise.all([
    fetch(`${API_INTERNAL_URL}/api/v1/macro/summary`, { cache: "no-store", signal: AbortSignal.timeout(20000) })
      .then((r) => (r.ok ? (r.json() as Promise<MacroSummary>) : null))
      .catch(() => null),
    fetch(`${API_INTERNAL_URL}/api/v1/macro/events`, { cache: "no-store", signal: AbortSignal.timeout(20000) })
      .then((r) => (r.ok ? (r.json() as Promise<{ events: EventRow[] }>) : null))
      .catch(() => null),
    fetch(`${API_INTERNAL_URL}/api/v1/macro/news`, { cache: "no-store", signal: AbortSignal.timeout(20000) })
      .then((r) => (r.ok ? (r.json() as Promise<{ articles: NewsArticle[] }>) : null))
      .catch(() => null),
  ]);

  if (!summary) {
    return (
      <p className="card p-5 border-[rgba(246,70,93,0.3)] bg-[var(--down-dim)] text-sm text-down">
        Macro API unreachable — check the scheduler and quant services.
      </p>
    );
  }

  const today = new Date().toISOString().slice(0, 10);
  const upcoming = (events?.events ?? []).filter((e) => e.event_date && e.event_date >= today);
  const recent = (events?.events ?? []).filter((e) => e.event_date && e.event_date < today).reverse().slice(0, 6);

  return (
    <>
      <section>
        <h2 className="mb-2 card-title text-muted">
          FRED macro series (FRED_API_KEY {summary.provider_health.fred.credentials_configured ? "configured" : "MISSING"})
        </h2>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          {summary.series.map((s) => {
            const v = s.value != null ? Number(s.value) : null;
            const chg = s.change;
            return (
              <div key={s.series_id} className="card bg-white/[0.02] p-3">
                <div className="text-[10px] text-muted">{SERIES_LABELS[s.series_id] ?? s.series_id}</div>
                <div className="mt-1 flex items-baseline gap-2">
                  <span className="text-lg font-semibold text-ink">
                    {v != null
                      ? v.toLocaleString("en-US", { maximumFractionDigits: Math.abs(v) < 100 ? 2 : 0 })
                      : "—"}
                  </span>
                  {chg != null && chg !== 0 && (
                    <span className={`text-[10px] ${chg > 0 ? "text-up" : "text-down"}`}>
                      {chg > 0 ? "▲" : "▼"} {Math.abs(chg).toFixed(2)}
                    </span>
                  )}
                </div>
                <div className="mt-1 num text-[10px] text-faint">
                  as of {s.as_of_date} · {s.units ?? ""}
                </div>
              </div>
            );
          })}
          {summary.series.length === 0 && (
            <p className="text-xs text-warn">No FRED data yet — scheduler will sync within minutes.</p>
          )}
        </div>
      </section>

      <section className="mt-6 grid grid-cols-1 gap-3 md:grid-cols-2">
        <div className="card p-5">
          <h2 className="card-title text-muted">
            CFTC futures-only COT — net non-commercial
          </h2>
          {summary.cftc.length === 0 ? (
            <p className="mt-2 text-xs text-warn">No CFTC data yet.</p>
          ) : (
            summary.cftc.map((c) => {
              const net = c.net_noncomm != null ? Number(c.net_noncomm) : null;
              const pctLong = c.details["pct_of_oi_noncomm_long"];
              const pctShort = c.details["pct_of_oi_noncomm_short"];
              return (
                <div key={c.series_id} className="mt-2 num text-xs">
                  <div className="flex justify-between">
                    <span className="text-ink-soft">{c.series_id.replace("COT_", "")}</span>
                    <span className={(net ?? 0) >= 0 ? "text-up" : "text-down"}>
                      net {net?.toLocaleString("en-US") ?? "—"}
                    </span>
                  </div>
                  <div className="text-[10px] text-faint">
                    report {c.as_of_date} · {pctLong ?? "—"}% long / {pctShort ?? "—"}% short of OI
                  </div>
                </div>
              );
            })
          )}
        </div>

        <div className="card p-5">
          <h2 className="card-title text-muted">
            Economic calendar (FRED release dates)
          </h2>
          <div className="mt-2 space-y-1 num text-xs">
            <div className="text-[10px] uppercase tracking-widest text-faint">upcoming</div>
            {upcoming.slice(0, 5).map((e) => (
              <div key={`${e.release_name}-${e.event_date}`} className="flex justify-between">
                <span className="text-ink-soft">{e.release_name}</span>
                <span className="text-muted">{e.event_date}</span>
              </div>
            ))}
            {upcoming.length === 0 && <p className="text-[10px] text-warn">No upcoming releases synced yet.</p>}
            <div className="pt-2 text-[10px] uppercase tracking-widest text-faint">recent</div>
            {recent.map((e) => (
              <div key={`${e.release_name}-${e.event_date}`} className="flex justify-between">
                <span className="text-muted">{e.release_name}</span>
                <span className="text-faint">{e.event_date}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="mt-6">
        <h2 className="mb-2 card-title text-muted">
          Market news (RSS · unclassified until the Phase 7 LLM lands)
        </h2>
        <div className="space-y-2">
          {(news?.articles ?? []).slice(0, 10).map((a) => (
            <div key={a.url} className="rounded border border-line bg-white/[0.02] p-3">
              <div className="flex items-baseline justify-between gap-3">
                <a
                  href={a.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-ink-soft hover:underline"
                >
                  {a.title}
                </a>
                <span className="shrink-0 num text-[10px] text-faint">
                  {a.source} · {a.published_at?.slice(0, 16).replace("T", " ") ?? "—"}
                </span>
              </div>
              {a.summary && <p className="mt-1 text-[10px] leading-snug text-muted">{a.summary.slice(0, 220)}</p>}
            </div>
          ))}
          {(news?.articles ?? []).length === 0 && (
            <p className="text-xs text-warn">No news synced yet — scheduler will fetch within minutes.</p>
          )}
        </div>
      </section>
    </>
  );
}

function MacroSkeleton() {
  return <div className="h-96 animate-pulse card animate-pulse opacity-60" />;
}

export default function MacroPage() {
  return (
    <main className="page rise">
      <div className="mx-auto max-w-5xl">
        <header className="mb-6">
          <h1 className="page-title">Macro Intelligence</h1>
          <p className="mt-1 text-xs text-muted">
            Phase 5 — FRED macro data, CFTC positioning, release calendar, news (all real, sourced & dated)
          </p>
        </header>
        <Suspense fallback={<MacroSkeleton />}>
          <MacroData />
        </Suspense>
        <footer className="mt-8 border-t border-line-subtle pt-4 text-[10.5px] text-faint">
          <a className="text-muted underline" href="/">← dashboard</a> ·
          macro observations are stored with fetch vintage; news content is untrusted input parsed to text only
        </footer>
      </div>
    </main>
  );
}
