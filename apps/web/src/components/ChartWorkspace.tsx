"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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

/* ------------------------------------------------------------------ */
/* Strategy layer registry (display metadata per strategy_id)          */
/* ------------------------------------------------------------------ */

interface LayerMeta {
  name: string;
  tag: string;
  category: string;
}

export const LAYERS: Record<string, LayerMeta> = {
  smc_liquidity_sweep: { name: "Liquidity Sweep", tag: "SWEEP", category: "Liquidity" },
  smc_eqh_eql: { name: "Equal Highs / Lows", tag: "EQH/EQL", category: "Liquidity" },
  ict_pdh_pdl: { name: "Prev Day/Week H-L", tag: "PDH/PDL", category: "Liquidity" },
  ict_asian_range: { name: "Asian Range", tag: "ASIA", category: "Liquidity" },
  ict_mss: { name: "MSS / CHoCH", tag: "MSS", category: "Market Structure" },
  smc_fvg: { name: "Fair Value Gap", tag: "FVG", category: "SMC / ICT" },
  smc_order_block: { name: "Order Block", tag: "OB", category: "SMC / ICT" },
  smc_breaker: { name: "Breaker Block", tag: "BREAK", category: "SMC / ICT" },
  smc_displacement: { name: "Displacement", tag: "DISP", category: "SMC / ICT" },
  smc_premium_discount: { name: "Premium / Discount", tag: "P/D", category: "SMC / ICT" },
  ict_fib_ote: { name: "Fibonacci / OTE", tag: "OTE", category: "SMC / ICT" },
  cross_market_smt: { name: "SMT Divergence", tag: "SMT", category: "SMC / ICT" },
  price_action_failed_breakout: { name: "Failed Breakout", tag: "F-BO", category: "Patterns" },
  wyckoff_spring: { name: "Wyckoff Spring", tag: "SPRING", category: "Wyckoff" },
  wyckoff_upthrust: { name: "Wyckoff Upthrust", tag: "UPTHR", category: "Wyckoff" },
  wyckoff_sos_sow: { name: "Wyckoff SOS / SOW", tag: "SOS", category: "Wyckoff" },
  ict_judas: { name: "Judas Swing", tag: "JUDAS", category: "Sessions" },
  ict_amd: { name: "AMD / Power of Three", tag: "AMD", category: "Sessions" },
  ict_silver_bullet: { name: "ICT Silver Bullet", tag: "SB", category: "Sessions" },
  ict_session_breakout: { name: "Session Range Breakout", tag: "S-BO", category: "Sessions" },
  ict_liquidity_void: { name: "Liquidity Void", tag: "VOID", category: "Liquidity" },
  quant_hidden_div: { name: "Hidden Divergence", tag: "H-DIV", category: "Quantitative" },
  quant_exhaustion: { name: "Trend Exhaustion", tag: "EXHAUST", category: "Quantitative" },
  quant_vol_regime: { name: "Volatility Regime", tag: "VOL", category: "Quantitative" },
};

const CATEGORY_ORDER = ["Market Structure", "Liquidity", "SMC / ICT", "Sessions", "Patterns", "Wyckoff", "Quantitative"];

const EMA_DEFS = [
  { key: "ema20", label: "EMA 20", color: "#7c5cff" },
  { key: "ema50", label: "EMA 50", color: "#e6b422" },
  { key: "ema200", label: "EMA 200", color: "#8a8f98" },
] as const;

export const TIMEFRAMES = [
  { interval: "5min", label: "5m" },
  { interval: "15min", label: "15m" },
  { interval: "30min", label: "30m" },
  { interval: "1h", label: "1H" },
  { interval: "4h", label: "4H" },
  { interval: "1day", label: "1D" },
] as const;

type TimeframeInterval = (typeof TIMEFRAMES)[number]["interval"];

interface Candle {
  market_ts: string;
  open: string;
  high: string;
  low: string;
  close: string;
}

interface Detection {
  strategy_id: string;
  algo_version: string;
  interval?: string;
  direction: string;
  status: string;
  anchor_time: string;
  levels: Record<string, number | null>;
  evidence: string[];
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

const LAYER_STORAGE_KEY = "pmi-chart-layers";
const defaultLayers = (): Record<string, boolean> => {
  const m: Record<string, boolean> = {};
  for (const id of Object.keys(LAYERS)) m[id] = false;
  // sensible defaults: the core three
  m.smc_liquidity_sweep = true;
  m.ict_mss = true;
  m.smc_fvg = true;
  return m;
};

const dirColor = (d: string) =>
  d === "bullish" ? "#059669" : d === "bearish" ? "#e11d48" : "#8a8f98";

export function ChartWorkspace() {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const emaRefs = useRef<Record<string, ISeriesApi<"Line">>>({});
  const markersRef = useRef<ReturnType<typeof createSeriesMarkers<Time>> | null>(null);
  const priceLineRefs = useRef<{ series: ISeriesApi<"Candlestick">; lines: ReturnType<ISeriesApi<"Candlestick">["createPriceLine"]>[] }>({ series: null as unknown as ISeriesApi<"Candlestick">, lines: [] });

  const [interval, setInterval_] = useState<TimeframeInterval>("1h");
  const [detections, setDetections] = useState<Detection[]>([]);
  const [verdicts, setVerdicts] = useState<StrategyVerdict[]>([]);
  const [verdictsAt, setVerdictsAt] = useState<string | null>(null);
  const [selected, setSelected] = useState<Detection | null>(null);
  const [layers, setLayers] = useState<Record<string, boolean>>(defaultLayers);
  const [showEma, setShowEma] = useState<Record<string, boolean>>({ ema20: true, ema50: true, ema200: false });
  const [count, setCount] = useState(0);
  const [lastTs, setLastTs] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // load saved layers
  useEffect(() => {
    try {
      const raw = localStorage.getItem(LAYER_STORAGE_KEY);
      if (raw) setLayers({ ...defaultLayers(), ...(JSON.parse(raw) as Record<string, boolean>) });
    } catch {
      /* first run */
    }
  }, []);
  const setLayer = (id: string, on: boolean) => {
    setLayers((prev) => {
      const next = { ...prev, [id]: on };
      try {
        localStorage.setItem(LAYER_STORAGE_KEY, JSON.stringify(next));
      } catch {
        /* ignore */
      }
      return next;
    });
  };
  const setCategory = (category: string, on: boolean) => {
    setLayers((prev) => {
      const next = { ...prev };
      for (const [id, meta] of Object.entries(LAYERS)) if (meta.category === category) next[id] = on;
      try {
        localStorage.setItem(LAYER_STORAGE_KEY, JSON.stringify(next));
      } catch {
        /* ignore */
      }
      return next;
    });
  };

  /* ---------------- chart lifecycle ---------------- */
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const css = () => getComputedStyle(document.documentElement);
    const themeOpts = () => {
      const c = css();
      return {
        layout: { textColor: c.getPropertyValue("--chart-text").trim() || "#6d7480" },
        grid: {
          vertLines: { color: c.getPropertyValue("--chart-grid").trim() },
          horzLines: { color: c.getPropertyValue("--chart-grid").trim() },
        },
        timeScale: { borderColor: c.getPropertyValue("--line").trim() },
        rightPriceScale: { borderColor: c.getPropertyValue("--line").trim() },
      };
    };
    const c = css();
    const chart = createChart(el, {
      layout: {
        background: { color: "transparent" },
        textColor: c.getPropertyValue("--chart-text").trim() || "#6d7480",
        fontFamily: "var(--font-geist-mono), monospace",
        fontSize: 11,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: c.getPropertyValue("--chart-grid").trim() },
        horzLines: { color: c.getPropertyValue("--chart-grid").trim() },
      },
      width: el.clientWidth,
      height: 460,
      timeScale: { borderColor: c.getPropertyValue("--line").trim(), timeVisible: true },
      rightPriceScale: { borderColor: c.getPropertyValue("--line").trim() },
      crosshair: {
        vertLine: { color: "rgba(199,143,10,0.4)", labelBackgroundColor: "#b8860b" },
        horzLine: { color: "rgba(199,143,10,0.4)", labelBackgroundColor: "#b8860b" },
      },
    });
    chartRef.current = chart;
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: c.getPropertyValue("--chart-up").trim() || "#059669",
      downColor: c.getPropertyValue("--chart-down").trim() || "#e11d48",
      borderVisible: false,
      wickUpColor: c.getPropertyValue("--chart-up").trim() || "#059669",
      wickDownColor: c.getPropertyValue("--chart-down").trim() || "#e11d48",
    });
    candleRef.current = candles;
    priceLineRefs.current.series = candles;
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
    const themeObserver = new MutationObserver(() => chart.applyOptions(themeOpts()));
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => {
      observer.disconnect();
      themeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      markersRef.current = null;
      priceLineRefs.current = { series: null as unknown as ISeriesApi<"Candlestick">, lines: [] };
      emaRefs.current = {};
    };
  }, []);

  /* ---------------- data loading ---------------- */
  const loadCandles = useCallback(
    async (tf: TimeframeInterval) => {
      setError(null);
      try {
        const [candleRes, detRes, verdictRes] = await Promise.all([
          fetch(`${API_URL}/api/v1/markets/XAUUSD/candles?interval=${tf}&limit=1500`).then((r) => {
            if (!r.ok) throw new Error(`candles ${r.status}`);
            return r.json() as Promise<{ candles: Candle[] }>;
          }),
          fetch(`${API_URL}/api/v1/strategies/detections?symbol=XAUUSD&interval=${tf}&limit=400`)
            .then((r) => (r.ok ? (r.json() as Promise<{ detections: Detection[] }>) : null))
            .catch(() => null),
          fetch(`${API_URL}/api/v1/strategy-verdicts/latest?symbol=XAUUSD&interval=${tf}`)
            .then((r) => (r.ok ? (r.json() as Promise<{ verdicts: StrategyVerdict[]; created_at: string }>) : null))
            .catch(() => null),
        ]);
        const bars = candleRes.candles.map((c) => ({
          time: (new Date(c.market_ts).getTime() / 1000) as UTCTimestamp,
          open: Number(c.open),
          high: Number(c.high),
          low: Number(c.low),
          close: Number(c.close),
        }));
        candleRef.current?.setData(bars);
        setCount(bars.length);
        setLastTs(candleRes.candles.at(-1)?.market_ts ?? null);
        chartRef.current?.timeScale().fitContent();
        setDetections(detRes?.detections ?? []);
        setVerdicts(verdictRes?.verdicts ?? []);
        setVerdictsAt(verdictRes?.created_at ?? null);
      } catch (e) {
        setError(e instanceof Error ? e.message : "failed to load chart data");
      }
    },
    [],
  );

  useEffect(() => {
    void loadCandles(interval);
  }, [interval, loadCandles]);

  // EMA overlays follow the candles (computed client-side for the workspace)
  useEffect(() => {
    const apply = async () => {
      const res = await fetch(`${API_URL}/api/v1/markets/XAUUSD/indicators?interval=${interval}`)
        .then((r) => (r.ok ? (r.json() as Promise<{ series_tail: Record<string, { time: string; value: number }[]> }> | null) : null))
        .catch(() => null);
      if (!res?.series_tail) return;
      for (const def of EMA_DEFS) {
        const pts = res.series_tail[def.key] ?? [];
        emaRefs.current[def.key]?.setData(
          pts.map((p) => ({ time: (new Date(p.time).getTime() / 1000) as UTCTimestamp, value: p.value })),
        );
      }
    };
    void apply();
  }, [interval, count]);

  /* ---------------- markers + price lines from enabled layers ---------------- */
  useEffect(() => {
    if (!candleRef.current || !markersRef.current) return;

    const enabled = Object.entries(layers).filter(([, on]) => on).map(([id]) => id);
    const byStrategy = new Map<string, Detection[]>();
    for (const d of detections) {
      if (!enabled.includes(d.strategy_id)) continue;
      const list = byStrategy.get(d.strategy_id) ?? [];
      list.push(d);
      byStrategy.set(d.strategy_id, list);
    }

    // markers: newest 120 per enabled strategy, capped overall
    const markers: SeriesMarker<Time>[] = [];
    const PER = 40;
    for (const [sid, list] of byStrategy) {
      const meta = LAYERS[sid];
      if (!meta) continue;
      for (const d of list.slice(0, PER)) {
        markers.push({
          time: (new Date(d.anchor_time).getTime() / 1000) as UTCTimestamp,
          position: d.direction === "bullish" ? "belowBar" : d.direction === "bearish" ? "aboveBar" : "inBar",
          color: dirColor(d.direction),
          shape: d.direction === "bullish" ? "arrowUp" : d.direction === "bearish" ? "arrowDown" : "circle",
          text: meta.tag,
        });
      }
    }
    markers.sort((a, b) => (a.time as number) - (b.time as number));
    markersRef.current.setMarkers(markers);

    // price lines: latest detection per enabled strategy (reference + invalidation)
    for (const line of priceLineRefs.current.lines) {
      candleRef.current.removePriceLine(line);
    }
    const lines: ReturnType<ISeriesApi<"Candlestick">["createPriceLine"]>[] = [];
    for (const [sid, list] of byStrategy) {
      const meta = LAYERS[sid];
      const latest = list[0];
      if (!meta || !latest) continue;
      const refKeys = ["overlap_low", "entry_low", "sweep_low", "level", "low"] as const;
      const ref = refKeys.map((k) => latest.levels[k]).find((v) => v != null);
      if (ref != null) {
        lines.push(
          candleRef.current.createPriceLine({
            price: ref,
            color: dirColor(latest.direction),
            lineWidth: 1,
            lineStyle: 0,
            axisLabelVisible: true,
            title: meta.tag,
          }),
        );
      }
      if (latest.levels.stop != null) {
        lines.push(
          candleRef.current.createPriceLine({
            price: latest.levels.stop,
            color: dirColor(latest.direction),
            lineWidth: 1,
            lineStyle: 2,
            axisLabelVisible: true,
            title: `${meta.tag} SL`,
          }),
        );
      }
    }
    priceLineRefs.current.lines = lines;
  }, [layers, detections]);

  const focusTime = useCallback((iso: string) => {
    const chart = chartRef.current;
    if (!chart) return;
    const t = new Date(iso).getTime() / 1000;
    chart.timeScale().setVisibleLogicalRange({ from: t - 60 * 60 * 48, to: t + 60 * 60 * 24 });
  }, []);

  const viewOnChart = useCallback(
    (d: Detection) => {
      setSelected(d);
      focusTime(d.anchor_time);
    },
    [focusTime],
  );

  /* ---------------- verdict table (below chart) ---------------- */
  const verdictRows = useMemo(() => {
    const lastByStrategy = new Map<string, Detection>();
    for (const d of detections) if (!lastByStrategy.has(d.strategy_id)) lastByStrategy.set(d.strategy_id, d);
    return verdicts.map((v) => ({ ...v, detection: lastByStrategy.get(v.strategy_id) ?? null }));
  }, [verdicts, detections]);

  const verdictPill = (v: string) =>
    v === "BULLISH" ? "pill-up" : v === "BEARISH" ? "pill-down" : v === "NEUTRAL" ? "pill-warn" : "";

  return (
    <div className="space-y-4">
      {/* header row */}
      <div className="card p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-baseline gap-3">
            <span className="text-[15px] font-semibold tracking-tight text-ink">XAU/USD</span>
            <span className="num text-[11px] text-faint">
              {count} candles{lastTs ? ` · last ${new Date(lastTs).toISOString().slice(5, 16)}Z` : ""}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-1">
            {EMA_DEFS.map((def) => (
              <button
                key={def.key}
                onClick={() => setShowEma((s) => ({ ...s, [def.key]: !s[def.key] }))}
                className={`rounded-md border px-2 py-1 text-[10.5px] font-medium transition-all ${showEma[def.key] ? "border-transparent text-white" : "border-line text-muted hover:text-ink"}`}
                style={showEma[def.key] ? { background: def.color } : {}}
              >
                {def.label}
              </button>
            ))}
            <span className="mx-1 h-4 w-px bg-line" aria-hidden />
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf.interval}
                onClick={() => setInterval_(tf.interval)}
                className={`rounded-md px-2 py-1 text-[11.5px] font-medium transition-all ${
                  interval === tf.interval ? "bg-gold-dim text-gold-bright" : "text-muted hover:bg-black/5 hover:text-ink dark:hover:bg-white/5"
                }`}
              >
                {tf.label}
              </button>
            ))}
          </div>
        </div>
        {error ? (
          <p className="mt-4 text-xs text-down">Failed to load chart data: {error}</p>
        ) : (
          <div ref={containerRef} className="mt-3" />
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
        {/* layers panel */}
        <div className="card h-fit p-4">
          <div className="flex items-center justify-between">
            <h3 className="card-title">Strategy layers</h3>
            <button
              onClick={() => setLayers(defaultLayers())}
              className="text-[10.5px] font-medium text-gold hover:underline"
            >
              reset
            </button>
          </div>
          {CATEGORY_ORDER.map((cat) => (
            <div key={cat} className="mt-3">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold text-ink-soft">{cat}</span>
                <button
                  onClick={() => setCategory(cat, !Object.entries(LAYERS).filter(([, m]) => m.category === cat).every(([id]) => layers[id]))}
                  className="text-[10px] text-muted hover:text-ink"
                >
                  {Object.entries(LAYERS).filter(([, m]) => m.category === cat).every(([id]) => layers[id]) ? "hide all" : "show all"}
                </button>
              </div>
              <div className="mt-1 space-y-0.5">
                {Object.entries(LAYERS)
                  .filter(([, m]) => m.category === cat)
                  .map(([id, meta]) => (
                    <label key={id} className="flex cursor-pointer items-center justify-between rounded-md px-1.5 py-1 hover:bg-black/[0.03] dark:hover:bg-white/[0.03]">
                      <span className="flex items-center gap-2 text-[12px] text-ink-soft">
                        <input
                          type="checkbox"
                          checked={!!layers[id]}
                          onChange={(e) => setLayer(id, e.target.checked)}
                          className="h-3.5 w-3.5 accent-[#b8860b]"
                        />
                        {meta.name}
                      </span>
                      <span className="num text-[9px] text-faint">{meta.tag}</span>
                    </label>
                  ))}
              </div>
            </div>
          ))}
          <p className="mt-3 text-[10px] leading-relaxed text-faint">
            Markers show where each strategy detected a signal. Price lines show the latest
            detection's reference level (solid) and invalidation (dashed).
          </p>
        </div>

        {/* verdicts + detail */}
        <div className="space-y-4">
          {/* detail panel */}
          {selected && (
            <div className="card p-5">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-[14px] font-semibold text-ink">
                      {LAYERS[selected.strategy_id]?.name ?? selected.strategy_id}
                    </span>
                    <span className={`pill ${selected.direction === "bullish" ? "pill-up" : "pill-down"}`}>
                      {selected.direction?.toUpperCase()}
                    </span>
                    <span className="pill">{selected.status}</span>
                  </div>
                  <div className="num mt-1 text-[11px] text-faint">
                    anchored {new Date(selected.anchor_time).toISOString().slice(5, 16).replace("T", " ")}Z · {selected.interval} · algo {selected.algo_version}
                  </div>
                </div>
                <button onClick={() => setSelected(null)} className="text-[11px] text-muted hover:text-ink">close</button>
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-3">
                {Object.entries(selected.levels)
                  .filter(([, v]) => v != null)
                  .slice(0, 6)
                  .map(([k, v]) => (
                    <div key={k} className="rounded-lg border border-line-subtle bg-raised px-3 py-2">
                      <div className="text-[10px] uppercase tracking-wide text-faint">{k.replace(/_/g, " ")}</div>
                      <div className="num text-[13px] font-medium text-ink">{Number(v).toFixed(2)}</div>
                    </div>
                  ))}
              </div>
              <div className="mt-3">
                <div className="card-title">Evidence</div>
                <ul className="mt-1.5 space-y-1">
                  {selected.evidence.map((e, i) => (
                    <li key={i} className="text-[12px] leading-relaxed text-muted">• {e}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {/* verdict table */}
          <div className="card overflow-hidden">
            <div className="flex items-center justify-between px-4 pt-4">
              <h3 className="card-title">Strategy verdicts — independent, computed from live data</h3>
              {verdictsAt && (
                <span className="num text-[10px] text-faint">
                  evaluated {new Date(verdictsAt).toISOString().slice(5, 16).replace("T", " ")}Z
                </span>
              )}
            </div>
            <div className="mt-2 overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Strategy</th>
                    <th>Verdict</th>
                    <th>Signal</th>
                    <th>Ref price</th>
                    <th>Evidence</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {verdictRows.map((v) => (
                    <tr key={v.strategy_id}>
                      <td className="font-medium text-ink">{v.strategy_name}</td>
                      <td>
                        <span className={`pill ${verdictPill(v.verdict)}`}>{v.verdict.replace("_", " ")}</span>
                      </td>
                      <td className="text-muted">{v.signal_status ?? "—"}</td>
                      <td className="num">{v.reference_price != null ? Number(v.reference_price).toFixed(2) : "—"}</td>
                      <td className="max-w-[280px] truncate text-muted" title={v.evidence[0]}>
                        {v.evidence[0] ?? "—"}
                      </td>
                      <td>
                        {v.detection ? (
                          <button
                            onClick={() => viewOnChart(v.detection!)}
                            className="btn btn-sm whitespace-nowrap"
                          >
                            View on chart
                          </button>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                  {verdictRows.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-4 py-6 text-center text-muted">
                        No verdict snapshot for this timeframe yet — the scheduler evaluates every 15 min, or
                        evaluate now from the Strategies page.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
