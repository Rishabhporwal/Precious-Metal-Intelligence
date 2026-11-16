"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  CandlestickSeries,
  LineSeries,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";

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
}

interface Detection {
  strategy_id: string;
  direction: string;
  status: string;
  anchor_time: string;
  levels: Record<string, number | null>;
  evidence: string[];
}

interface Candle {
  market_ts: string;
  open: string;
  high: string;
  low: string;
  close: string;
}

const TIMEFRAMES = [
  { interval: "1h", label: "1H" },
  { interval: "4h", label: "4H" },
  { interval: "1day", label: "1D" },
] as const;
type Tf = (typeof TIMEFRAMES)[number]["interval"];

const EMA_DEFS = [
  { key: "ema20", label: "EMA 20", color: "#60a5fa" },
  { key: "ema50", label: "EMA 50", color: "#f59e0b" },
];

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

const epoch = (ts: string): UTCTimestamp =>
  Math.floor(new Date(ts).getTime() / 1000) as UTCTimestamp;

export function StrategyLabView() {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const emaRefs = useRef<Record<string, ISeriesApi<"Line">>>({});
  const markersRef = useRef<ReturnType<typeof createSeriesMarkers<Time>> | null>(null);
  const priceLinesRef = useRef<ReturnType<ISeriesApi<"Candlestick">["createPriceLine"]>[]>([]);

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

  /* ---------------- chart lifecycle ---------------- */
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const css = () => getComputedStyle(document.documentElement);
    const chart = createChart(el, {
      layout: {
        background: { color: "transparent" },
        textColor: css().getPropertyValue("--chart-text").trim() || "#6d7480",
        fontFamily: "var(--font-geist-mono), monospace",
        fontSize: 11,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: css().getPropertyValue("--chart-grid").trim() },
        horzLines: { color: css().getPropertyValue("--chart-grid").trim() },
      },
      width: el.clientWidth,
      height: 440,
      timeScale: { borderColor: css().getPropertyValue("--line").trim(), timeVisible: true },
      rightPriceScale: { borderColor: css().getPropertyValue("--line").trim() },
      crosshair: {
        vertLine: { color: "rgba(199,143,10,0.4)", labelBackgroundColor: "#b8860b" },
        horzLine: { color: "rgba(199,143,10,0.4)", labelBackgroundColor: "#b8860b" },
      },
    });
    chartRef.current = chart;
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: css().getPropertyValue("--chart-up").trim() || "#059669",
      downColor: css().getPropertyValue("--chart-down").trim() || "#e11d48",
      borderVisible: false,
      wickUpColor: css().getPropertyValue("--chart-up").trim() || "#059669",
      wickDownColor: css().getPropertyValue("--chart-down").trim() || "#e11d48",
    });
    candleRef.current = candles;
    markersRef.current = createSeriesMarkers(candles, []);
    for (const def of EMA_DEFS) {
      emaRefs.current[def.key] = chart.addSeries(LineSeries, {
        color: def.color,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
    }
    const observer = new ResizeObserver(() => chart.applyOptions({ width: el.clientWidth }));
    observer.observe(el);
    // click a marker → focus that detection (refs: chart mounts ONCE)
    chart.subscribeClick((param) => {
      const t = param.time as UTCTimestamp | undefined;
      const sel = selectedRef.current;
      if (t == null || !sel) return;
      const clicked = detectionsRef.current
        .filter((d) => d.strategy_id === sel)
        .find((d) => epoch(d.anchor_time) === t);
      if (clicked) setFocused(clicked);
    });
    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      markersRef.current = null;
    };
  }, []);

  /* ---------------- data loading ---------------- */
  useEffect(() => {
    let cancelled = false;
    const candleEl = candleRef.current;
    if (!candleEl) return;
    fetch(`${API_URL}/api/v1/markets/XAUUSD/candles?interval=${tf}&limit=400`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("candles unavailable"))))
      .then((d: { candles: Candle[] }) => {
        if (cancelled) return;
        candleEl.setData(
          d.candles.map((c) => ({
            time: epoch(c.market_ts),
            open: Number(c.open),
            high: Number(c.high),
            low: Number(c.low),
            close: Number(c.close),
          })),
        );
        chartRef.current?.timeScale().fitContent();
      })
      .catch(() => setError("Could not load candles — the data service may be restarting."));

    fetch(`${API_URL}/api/v1/markets/XAUUSD/indicators?interval=${tf}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (cancelled || !d) return;
        const tail = d.series_tail ?? {};
        for (const def of EMA_DEFS) {
          const series = tail[def.key] ?? [];
          emaRefs.current[def.key]?.setData(
            series
              .filter((p: { value: number | null }) => p.value != null)
              .map((p: { time: string; value: number }) => ({
                time: epoch(p.time),
                value: p.value,
              })),
          );
        }
      })
      .catch(() => undefined);

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
          // preselect the most interesting strategy: a bullish/bearish verdict, else first
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

  /* ---------------- markers + price lines for the selected strategy ---------------- */
  const selectedDetections = useMemo(
    () => detections.filter((d) => d.strategy_id === selected),
    [detections, selected],
  );

  useEffect(() => {
    const candles = candleRef.current;
    const markersApi = markersRef.current;
    if (!candles || !markersApi) return;
    // clear old price lines
    for (const line of priceLinesRef.current) candles.removePriceLine(line);
    priceLinesRef.current = [];
    if (!selected) {
      markersApi.setMarkers([]);
      return;
    }
    const markers: SeriesMarker<Time>[] = selectedDetections.map((d) => ({
      time: epoch(d.anchor_time),
      position: d.direction === "bullish" ? "belowBar" : "aboveBar",
      shape: d.direction === "bullish" ? "arrowUp" : d.direction === "bearish" ? "arrowDown" : "circle",
      color: d.direction === "bullish" ? "#10b981" : d.direction === "bearish" ? "#f6465d" : "#9ca3af",
      text: d.direction === "bullish" ? "Buy signal" : d.direction === "bearish" ? "Sell signal" : "",
      size: 1,
    }));
    markersApi.setMarkers(markers);
    if (markers.length) {
      const times = markers.map((m) => m.time as number);
      chartRef.current?.timeScale().setVisibleLogicalRange({
        from: Math.max(0, times.length - 60),
        to: times.length + 12,
      });
    }
    // levels of the latest detection as horizontal lines
    const latest = selectedDetections[0];
    if (latest) {
      const labels: [string, number, string][] = Object.entries(latest.levels)
        .filter(([, v]) => typeof v === "number")
        .filter(([k]) => !k.startsWith("ema"))
        .slice(0, 3)
        .map(([k, v]) => [k, v as number, ""]);
      for (const [key, value, title] of labels) {
        priceLinesRef.current.push(
          candles.createPriceLine({
            price: value,
            color: key.includes("stop") || key.includes("invalid") ? "#f6465d" : "#b8860b",
            lineWidth: 1,
            lineStyle: 2,
            axisLabelVisible: true,
            title: title || key.replace(/_/g, " "),
          }),
        );
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
            <div className="mt-2 flex items-center gap-1.5">
              {TIMEFRAMES.map((t) => (
                <button
                  key={t.interval}
                  onClick={() => setTf(t.interval)}
                  className={`rounded-md px-2 py-0.5 text-[11.5px] font-medium transition-all ${
                    tf === t.interval
                      ? "bg-gold-dim text-gold-bright"
                      : "text-muted hover:bg-black/5 hover:text-ink dark:hover:bg-white/5"
                  }`}
                >
                  {t.label}
                </button>
              ))}
              <span className="ml-auto text-[10.5px] text-faint">{filtered.length} of {strategies.length} strategies</span>
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
                  className={`block w-full border-b border-line-subtle px-3 py-2.5 text-left transition-colors ${
                    active ? "bg-gold-dim/40" : "hover:bg-black/5 dark:hover:bg-white/5"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className={`text-[12.5px] font-medium ${active ? "text-ink" : "text-muted"}`}>
                      {s.name}
                    </span>
                    <span className={`pill ${chip.cls} shrink-0`}>{chip.label}</span>
                  </div>
                  {v?.last_detection && (
                    <div className="mt-0.5 text-[10.5px] text-faint">last signal {ageOf(v.last_detection)}</div>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* CHART + DETAILS */}
        <div className="space-y-3">
          <div className="card p-2">
            <div ref={containerRef} className="w-full" />
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
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <div className="rounded-xl border border-line-subtle bg-raised p-3.5">
                    <div className="text-[11.5px] text-muted">What it means</div>
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
                    <div className="text-[11.5px] text-muted">
                      Signals on the {tf} chart — click an arrow on the chart to inspect it
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
                                {d.anchor_time.slice(5, 16).replace("T", " ")} UTC
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
