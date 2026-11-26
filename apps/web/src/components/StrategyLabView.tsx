"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { fmtUaeDateTime } from "@/lib/time";
import { Vela } from "@luxalgo/vela";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface StrategyInfo {
  strategy_id: string;
  name: string;
  description: string;
  enabled?: boolean;
}

interface StrategyVerdict {
  strategy_id: string;
  strategy_name: string;
  verdict: string;
  signal_status: string | null;
  direction: string | null;
  reference_price: number | null;
  invalidation_level: number | null;
  evidence: string[];
  last_detection: string | null;
  conditions_met?: string[];
  conditions_missing?: string[];
  data_quality?: string;
}

interface Detection {
  strategy_id: string;
  direction: string;
  status: string;
  anchor_time: string;
  levels: Record<string, number | null>;
  evidence: string[];
}

/* ------------------------------------------------------------------ */
/* Vela timeframe map + custom provider over our own candle API        */
/* ------------------------------------------------------------------ */

const VELA_TF: Record<string, string> = {
  "1h": "60",
  "4h": "240",
  "1day": "1D",
};

interface PmiBar {
  time: number; // epoch ms, bar OPEN time
  open: number;
  high: number;
  low: number;
  close: number;
}

function makePmiProvider() {
  const cache = new Map<string, PmiBar[]>();
  return {
    async getBars(ticker: string, timeframe: string, range?: { from?: number; to?: number; limit?: number }) {
      const interval = ticker === "XAUUSD" ? tfToInterval(timeframe) : null;
      if (!interval) return [];
      const limit = Math.min(range?.limit ?? 500, 1000);
      const bars = await loadBars(interval, limit);
      cache.set(`${interval}`, bars);
      let out = bars;
      if (range?.from != null) out = bars.filter((b) => b.time >= range.from!);
      if (range?.to != null) out = out.filter((b) => b.time <= range.to!);
      return out;
    },
    async listSymbols() {
      return [{ ticker: "XAUUSD", description: "Gold spot / US dollar", type: "forex" }];
    },
    async getSymbolInfo(ticker: string) {
      if (ticker !== "XAUUSD") return undefined;
      return {
        ticker,
        timezone: "Etc/UTC",
        session: "24x7",
        volume: false,
        timeframes: { finest: "60", default: "60", list: ["60", "240", "1D"] },
      };
    },
  };
}

function tfToInterval(tf: string): string | null {
  switch (tf) {
    case "60":
      return "1h";
    case "240":
      return "4h";
    case "1D":
      return "1day";
    default:
      return null;
  }
}

async function loadBars(interval: string, limit: number): Promise<PmiBar[]> {
  const res = await fetch(
    `${API_URL}/api/v1/markets/XAUUSD/candles?interval=${interval}&limit=${limit}`,
  );
  if (!res.ok) throw new Error("candles unavailable");
  const d = (await res.json()) as {
    candles: { market_ts: string; open: string; high: string; low: string; close: string }[];
  };
  const seen = new Set<number>();
  const bars: PmiBar[] = [];
  for (const c of d.candles) {
    const time = new Date(c.market_ts).getTime();
    if (seen.has(time)) continue;
    seen.add(time);
    bars.push({
      time,
      open: Number(c.open),
      high: Number(c.high),
      low: Number(c.low),
      close: Number(c.close),
    });
  }
  bars.sort((a, b) => a.time - b.time);
  return bars;
}

/* ------------------------------------------------------------------ */

const TIMEFRAMES = [
  { interval: "1h", label: "1H" },
  { interval: "4h", label: "4H" },
  { interval: "1day", label: "1D" },
] as const;
type Tf = (typeof TIMEFRAMES)[number]["interval"];

function verdictChip(v: string | undefined): { label: string; cls: string } {
  switch (v) {
    case "BULLISH":
      return { label: "Bullish", cls: "pill-up" };
    case "BEARISH":
      return { label: "Bearish", cls: "pill-down" };
    case "NEUTRAL":
      return { label: "Neutral", cls: "" };
    case "WAITING_FOR_CONFIRMATION":
      return { label: "Waiting for confirmation", cls: "pill-warn" };
    case "INSUFFICIENT_DATA":
      return { label: "Not enough data", cls: "" };
    default:
      return { label: "Quiet", cls: "" };
  }
}

const ageOf = (ts: string | null): string => {
  if (!ts) return "—";
  const mins = Math.max(0, (Date.now() - new Date(ts).getTime()) / 60000);
  if (mins < 60) return `${Math.round(mins)}m ago`;
  if (mins < 60 * 24) return `${Math.round(mins / 60)}h ago`;
  return `${Math.round(mins / 1440)}d ago`;
};

function resolveVelaTheme(): Record<string, string> {
  if (typeof document === "undefined") return { theme: "dark" };
  const css = getComputedStyle(document.documentElement);
  const v = (name: string, fb: string) => css.getPropertyValue(name).trim() || fb;
  const dark = document.documentElement.classList.contains("dark");
  return {
    background: v("--bg-elev", dark ? "#141821" : "#ffffff"),
    textColor: v("--chart-text", "#6d7480"),
    gridColor: v("--chart-grid", dark ? "rgba(255,255,255,0.03)" : "rgba(20,30,50,0.06)"),
    borderColor: v("--line", dark ? "rgba(255,255,255,0.08)" : "rgba(20,30,50,0.1)"),
    upColor: v("--chart-up", "#059669"),
    downColor: v("--chart-down", "#e11d48"),
    fontFamily: 'var(--font-geist-mono), ui-monospace, SFMono-Regular, monospace',
  };
}

export function StrategyLabView() {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<Vela | null>(null);
  const overlayIdsRef = useRef<string[]>([]);

  const [tf, setTf] = useState<Tf>("1h");
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const [verdicts, setVerdicts] = useState<Record<string, StrategyVerdict>>({});
  const [detections, setDetections] = useState<Detection[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [focused, setFocused] = useState<Detection | null>(null);
  const selectedRef = useRef<string | null>(null);
  const detectionsRef = useRef<Detection[]>([]);
  selectedRef.current = selected;
  detectionsRef.current = detections;
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);

  /* ---------------- chart lifecycle (mounts once) ---------------- */
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    let disposed = false;
    const chart = new Vela(el, {
      symbol: "XAUUSD",
      timeframe: VELA_TF["1h"],
      theme: resolveVelaTheme() as never,
      bars: 400,
    });
    chartRef.current = chart;
    chart.drawings.showToolbar(false); // our overlays only — no user drawing chrome
    chart.data.registerProvider("pmi", makePmiProvider());
    chart.ready().catch(() => {
      if (!disposed) setError("Could not load candles — the data service may be restarting.");
    });
    return () => {
      disposed = true;
      overlayIdsRef.current = [];
      chartRef.current = null;
      try {
        chart.destroy?.();
      } catch {
        /* older builds expose .remove() */
        try {
          (chart as unknown as { remove?: () => void }).remove?.();
        } catch {
          /* ignore */
        }
      }
    };
  }, []);

  /* ---------------- timeframe change → reload via provider ---------------- */
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    (chart as unknown as { setMarket?: (s: { symbol: string; timeframe: string }) => void }).setMarket?.({
      symbol: "XAUUSD",
      timeframe: VELA_TF[tf],
    });
  }, [tf]);

  /* ---------------- data loading ---------------- */
  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/api/v1/strategies/detections?symbol=XAUUSD&interval=${tf}&limit=400`)
      .then((r) => (r.ok ? r.json() : { detections: [] }))
      .then((d) => !cancelled && setDetections(d.detections ?? []))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [tf]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetch(`${API_URL}/api/v1/strategies`).then((r) => (r.ok ? r.json() : { strategies: [] })),
      fetch(`${API_URL}/api/v1/strategy-verdicts/latest?symbol=XAUUSD&interval=1h`).then((r) =>
        r.ok ? r.json() : { verdicts: [] },
      ),
    ])
      .then(([s, v]) => {
        if (cancelled) return;
        setStrategies((s.strategies ?? []).filter((x: StrategyInfo) => x.enabled !== false));
        const map: Record<string, StrategyVerdict> = {};
        for (const ver of v.verdicts ?? []) map[ver.strategy_id] = ver;
        setVerdicts(map);
        if (!cancelled && (s.strategies ?? []).length && !selected) {
          const first = (s.strategies as StrategyInfo[]).find((x) => {
            const ver = map[x.strategy_id];
            return ver?.verdict === "BULLISH" || ver?.verdict === "BEARISH";
          });
          setSelected(first?.strategy_id ?? (s.strategies as StrategyInfo[])[0]?.strategy_id ?? null);
        }
      })
      .catch(() => !cancelled && setError("Could not load strategies."));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ---------------- markers + level lines for the selected strategy ---------------- */
  const selectedDetections = useMemo(
    () => detections.filter((d) => d.strategy_id === selected),
    [detections, selected],
  );

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const drawings = (
      chart as unknown as {
        drawings: {
          add: (type: string, spec: Record<string, unknown>) => { id: string } | null;
          remove: (id: string) => void;
          lock: (id: string) => void;
          clear: () => void;
        };
      }
    ).drawings;

    // clear previous overlay group
    for (const id of overlayIdsRef.current) {
      try {
        drawings.remove(id);
      } catch {
        /* already gone */
      }
    }
    overlayIdsRef.current = [];

    const addLocked = (type: string, spec: Record<string, unknown>) => {
      const d = drawings.add(type, spec);
      if (d?.id) {
        try {
          drawings.lock(d.id);
        } catch {
          /* lock unsupported — cosmetic only */
        }
        overlayIdsRef.current.push(d.id);
      }
    };

    const ms = (ts: string) => new Date(ts).getTime();

    // detection arrows
    for (const d of selectedDetections.slice(-14)) {
      const price = Object.values(d.levels).find((v) => typeof v === "number") ?? null;
      addLocked(d.direction === "bullish" ? "arrowmarkup" : "arrowmarkdown", {
        paneId: "price",
        size: "small",
        anchors: [{ time: ms(d.anchor_time), price: price ?? undefined }],
        props: { size: "small" },
      });
    }

    // latest detection's levels as horizontal lines
    const latest = selectedDetections[selectedDetections.length - 1];
    const lastTime = detectionsRef.current.length ? ms(latest?.anchor_time ?? new Date().toISOString()) : Date.now();
    if (latest) {
      const labels: [string, number][] = Object.entries(latest.levels)
        .filter(([, v]) => typeof v === "number")
        .filter(([k]) => !k.startsWith("ema"))
        .slice(0, 3)
        .map(([k, v]) => [k, v as number]);
      for (const [key, value] of labels) {
        addLocked("hline", {
          paneId: "price",
          anchors: [{ time: lastTime, price: value }],
          props: {
            style: {
              lineColor: key.includes("stop") || key.includes("invalid") ? "#f6465d" : "#b8860b",
              lineWidth: 1,
              lineStyle: "dashed",
            },
            label: key.replace(/_/g, " "),
          },
        });
      }
    }
  }, [selected, selectedDetections]);

  /* ---------------- derived ---------------- */
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const list = [...strategies].sort((a, b) => {
      const va = verdicts[a.strategy_id]?.verdict ?? "";
      const vb = verdicts[b.strategy_id]?.verdict ?? "";
      const rank = (x: string) => (x === "BULLISH" || x === "BEARISH" ? 0 : x === "WAITING_FOR_CONFIRMATION" ? 1 : 2);
      return rank(va) - rank(vb);
    });
    if (!q) return list;
    return list.filter(
      (s) => s.name.toLowerCase().includes(q) || s.strategy_id.toLowerCase().includes(q),
    );
  }, [strategies, verdicts, search]);

  const selVerdict = selected ? verdicts[selected] : undefined;
  const selStrategy = strategies.find((s) => s.strategy_id === selected);

  return (
    <div className="space-y-4">
      {error && (
        <div className="rounded-xl border border-line-subtle bg-raised p-4 text-[12.5px] text-muted">{error}</div>
      )}
      <div className="grid gap-4 lg:grid-cols-[300px_1fr]">
        {/* STRATEGY LIST */}
        <div className="card flex max-h-[620px] flex-col overflow-hidden">
          <div className="border-b border-line-subtle p-3">
            <input
              className="input w-full text-[12.5px]"
              placeholder="Search strategies…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <div className="mt-2 text-[10.5px] uppercase tracking-wider text-faint">
              {filtered.length} of {strategies.length} strategies
            </div>
          </div>
          <div className="flex-1 overflow-y-auto">
            {filtered.map((s) => {
              const v = verdicts[s.strategy_id];
              const chip = verdictChip(v?.verdict);
              const active = selected === s.strategy_id;
              return (
                <button
                  key={s.strategy_id}
                  onClick={() => {
                    setSelected(s.strategy_id);
                    setFocused(null);
                  }}
                  className={`relative block w-full border-b border-line-subtle px-3 py-2.5 pl-4 text-left transition-colors ${
                    active ? "bg-gold-dim" : "hover:bg-black/[0.03] dark:hover:bg-white/[0.04]"
                  }`}
                >
                  {active && <span className="absolute left-0 top-0 h-full w-[3px] bg-gold" />}
                  <div className="flex items-center justify-between gap-2">
                    <span className={`text-[12.5px] font-medium ${active ? "text-ink" : "text-muted"}`}>
                      {s.name}
                    </span>
                    <span
                      className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                        v?.verdict === "BULLISH"
                          ? "bg-up"
                          : v?.verdict === "BEARISH"
                            ? "bg-down"
                            : v?.verdict === "WAITING_FOR_CONFIRMATION"
                              ? "bg-warn"
                              : "bg-faint/40"
                      }`}
                      title={chip.label}
                    />
                  </div>
                  <div className="mt-0.5 flex items-center gap-2">
                    <span className={`pill ${chip.cls} !text-[10px] !px-1.5 !py-0`}>{chip.label}</span>
                    {v?.last_detection && (
                      <span className="text-[10px] text-faint">{ageOf(v.last_detection)}</span>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* CHART + DETAILS */}
        <div className="space-y-3">
          <div className="card overflow-hidden">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-line-subtle px-4 py-2.5">
              <div className="flex items-center gap-2">
                <span className="num text-[13px] font-bold tracking-tight text-ink">XAU/USD</span>
                <span className="rounded bg-black/[0.04] px-1.5 py-0.5 text-[9.5px] font-semibold uppercase tracking-wider text-faint dark:bg-white/[0.06]">
                  spot
                </span>
                <span className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-up">
                  <span className="relative flex h-1.5 w-1.5">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-up opacity-60" />
                    <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-up" />
                  </span>
                  live
                </span>
              </div>
              <div className="ml-auto flex rounded-lg border border-line-subtle bg-black/[0.03] p-0.5 dark:bg-white/[0.04]">
                {TIMEFRAMES.map((t) => (
                  <button
                    key={t.interval}
                    onClick={() => setTf(t.interval)}
                    className={`rounded-md px-2.5 py-1 text-[11.5px] font-semibold transition-all ${
                      tf === t.interval
                        ? "bg-gold-dim text-gold shadow-sm"
                        : "text-faint hover:text-ink"
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>
            <div ref={containerRef} className="h-[480px] w-full" />
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line-subtle px-4 py-2 text-[10.5px] text-faint">
              <span className="flex items-center gap-1"><span className="text-up">▲</span> buy signal</span>
              <span className="flex items-center gap-1"><span className="text-down">▼</span> sell signal</span>
              <span className="flex items-center gap-1"><span className="text-gold">╌</span> strategy level</span>
              <span className="flex items-center gap-1"><span className="text-down">╌</span> stop / invalidation</span>
              <span className="ml-auto hidden sm:inline">70+ indicators · right-click the chart</span>
            </div>
          </div>

          {/* OUTCOME / DETAIL PANEL */}
          {selected && (
            <div className="card p-5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[14px] font-semibold text-ink">
                  {selStrategy?.name ?? selected}
                </span>
                {selVerdict && (
                  <span className={`pill ${verdictChip(selVerdict.verdict).cls}`}>
                    {verdictChip(selVerdict.verdict).label}
                    {selVerdict.signal_status ? ` · ${selVerdict.signal_status.toLowerCase()}` : ""}
                  </span>
                )}
                {selVerdict?.last_detection && (
                  <span className="text-[11px] text-faint">last signal {ageOf(selVerdict.last_detection)}</span>
                )}
              </div>

              {selVerdict && (
                <div
                  className={`mt-3 rounded-xl border-l-4 bg-raised p-3.5 ${
                    selVerdict.verdict === "BULLISH"
                      ? "border-l-up"
                      : selVerdict.verdict === "BEARISH"
                        ? "border-l-down"
                        : "border-l-warn"
                  } border border-line-subtle`}
                >
                  <div className="text-[11px] uppercase tracking-wider text-faint">Current stance</div>
                  <div className="mt-1 text-[13.5px] font-semibold text-ink">
                    {selVerdict.signal_status === "CONFIRMED"
                      ? "CONFIRMED — all its conditions are met on the live chart."
                      : selVerdict.signal_status === "WAITING"
                        ? `Waiting — ${selVerdict.conditions_met?.length ?? 0} of ${(selVerdict.conditions_met?.length ?? 0) + (selVerdict.conditions_missing?.length ?? 0)} conditions met so far.`
                        : "No active signal — it is watching but not confident enough to call anything."}
                  </div>
                  <div className="mt-1 text-[11.5px] text-muted">
                    {selVerdict.data_quality === "FRESH"
                      ? "Running on live, up-to-date price data."
                      : selVerdict.data_quality
                        ? `Data quality: ${selVerdict.data_quality.toLowerCase()} — treat with care.`
                        : ""}
                  </div>
                </div>
              )}

              {selVerdict && (
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <div className="rounded-xl border border-line-subtle bg-raised p-3.5">
                    <div className="text-[11px] font-semibold uppercase tracking-wider text-faint">What it means</div>
                    <ul className="mt-1.5 space-y-1.5">
                      {(selVerdict.evidence.length
                        ? selVerdict.evidence
                        : ["No active signal — this strategy is watching the market."]
                      ).map((e, i) => (
                        <li key={i} className="flex gap-2 text-[12px] leading-relaxed text-muted">
                          <span className="text-gold">•</span>
                          <span>{e}</span>
                        </li>
                      ))}
                    </ul>
                    {selVerdict.invalidation_level != null && (
                      <div className="mt-2.5 text-[11.5px] text-muted">
                        This call is wrong if price crosses{" "}
                        <span className="num font-semibold text-ink">
                          ${selVerdict.invalidation_level.toFixed(2)}
                        </span>
                      </div>
                    )}
                  </div>
                  <div className="rounded-xl border border-line-subtle bg-raised p-3.5">
                    <div className="text-[11px] font-semibold uppercase tracking-wider text-faint">
                      Recent signals · {tf}
                    </div>
                    {selectedDetections.length ? (
                      <ul className="mt-1.5 space-y-2">
                        {selectedDetections.slice(0, 5).map((d, i) => (
                          <li
                            key={i}
                            className={`cursor-pointer rounded-lg border p-2 transition-colors ${
                              focused === d
                                ? "border-gold bg-gold-dim/30"
                                : "border-line-subtle hover:bg-black/5 dark:hover:bg-white/5"
                            }`}
                            onClick={() => setFocused(d)}
                          >
                            <div className="flex items-center justify-between gap-2">
                              <span
                                className={`text-[12px] font-semibold ${
                                  d.direction === "bullish" ? "text-up" : "text-down"
                                }`}
                              >
                                {d.direction === "bullish" ? "Buy" : "Sell"} signal
                              </span>
                              <span className="text-[10.5px] text-faint">
                                {fmtUaeDateTime(d.anchor_time)} UAE
                              </span>
                            </div>
                            {d.evidence.slice(0, 2).map((e, j) => (
                              <div key={j} className="mt-0.5 text-[11.5px] leading-relaxed text-muted">
                                {e}
                              </div>
                            ))}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <div className="mt-1.5 text-[12px] text-muted">
                        No signals in the current window — the strategy sees nothing worth acting on.
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
