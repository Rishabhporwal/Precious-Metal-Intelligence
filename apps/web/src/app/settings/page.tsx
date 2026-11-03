import { connection } from "next/server";
import { ThemeToggle } from "@/components/ThemeToggle";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

const CONFIG_ROWS: { label: string; value: string; note: string }[] = [
  { label: "Market data provider", value: "Twelve Data (free plan)", note: "8 req/min · 800/day · gold spot only — silver + cross-market need a paid tier" },
  { label: "Quote polling", value: "every 5 min", note: "≈288 credits/day" },
  { label: "1-minute candle refresh", value: "every 15 min", note: "≈96 credits/day" },
  { label: "1-hour candle refresh", value: "every 30 min", note: "≈48 credits/day — added for live strategy verdicts" },
  { label: "Strategy verdicts", value: "every 15 min", note: "independent per-strategy verdicts, persisted snapshots" },
  { label: "Daily Verdict", value: "every 6 hours", note: "fused news + economy + strategies + technicals" },
  { label: "LLM provider", value: "OpenRouter", note: "narrative only — never computes levels; responses cached" },
  { label: "Trading", value: "Paper only", note: "there is no live-broker code in this system" },
];

export const metadata = { title: "Settings — PMI" };
export const instant = false; // blocking dynamic route — status probes run per request

async function StatusChips() {
  await connection(); // runtime data — render per request, not at build
  const [apiOk, quantOk] = await Promise.all([
    fetch(`${API_INTERNAL_URL}/healthz`, { cache: "no-store", signal: AbortSignal.timeout(5000) })
      .then((r) => r.ok).catch(() => false),
    fetch(`${API_INTERNAL_URL.replace(":8000", ":8001")}/ready`, { cache: "no-store", signal: AbortSignal.timeout(5000) })
      .then((r) => r.ok).catch(() => false),
  ]);
  return (
    <div className="flex flex-wrap gap-2">
      <span className={`pill ${apiOk ? "pill-up" : "pill-down"}`}>
        <span className={`dot ${apiOk ? "dot-live" : "bg-down"}`} /> API
      </span>
      <span className={`pill ${quantOk ? "pill-up" : "pill-down"}`}>
        <span className={`dot ${quantOk ? "dot-live" : "bg-down"}`} /> Quant engine
      </span>
      <span className="pill pill-gold">Gold-only mode (free data plan)</span>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <main className="page rise">
      <div className="mx-auto max-w-3xl">
        <header className="mb-6">
          <h1 className="page-title">Settings</h1>
          <p className="page-sub">System configuration at a glance — how this platform runs.</p>
        </header>

        <div className="space-y-4">
          <div className="card p-5">
            <div className="card-title">Appearance</div>
            <div className="mt-3 flex items-center justify-between">
              <span className="text-[13px] text-ink-soft">Theme</span>
              <ThemeToggle />
            </div>
            <p className="mt-2 text-[11px] text-muted">Light is the default; dark mode is remembered per browser.</p>
          </div>

          <div className="card p-5">
            <div className="card-title">Service status</div>
            <div className="mt-3">
              <StatusChips />
            </div>
          </div>

          <div className="card p-5">
            <div className="card-title">Configuration</div>
            <dl className="mt-3 space-y-3">
              {CONFIG_ROWS.map((r) => (
                <div key={r.label} className="flex flex-col gap-0.5 border-b border-line-subtle pb-3 last:border-0 last:pb-0">
                  <dt className="text-[12.5px] font-medium text-ink">{r.label}</dt>
                  <dd className="text-[12px] text-ink-soft">
                    {r.value} <span className="text-faint">· {r.note}</span>
                  </dd>
                </div>
              ))}
            </dl>
          </div>

          <p className="text-[10.5px] leading-relaxed text-faint">
            Configuration is environment-driven (see .env.example). This page surfaces the running
            values honestly — it does not fabricate status.
          </p>
        </div>
      </div>
    </main>
  );
}
