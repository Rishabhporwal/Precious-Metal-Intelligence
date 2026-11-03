"use client";

import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  LineSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const TIMEFRAMES = [
  { interval: "1min", label: "1m" },
  { interval: "5min", label: "5m" },
  { interval: "15min", label: "15m" },
  { interval: "30min", label: "30m" },
  { interval: "1h", label: "1H" },
  { interval: "4h", label: "4H" },
  { interval: "1day", label: "1D" },
  { interval: "1week", label: "1W" },
  { interval: "1month", label: "1M" },
] as const;

export type TimeframeInterval = (typeof TIMEFRAMES)[number]["interval"];

interface Candle {
  market_ts: string;
  open: string;
  high: string;
  low: string;
  close: string;
  status: string;
}

interface IndicatorPoint {
  time: string;
  value: number;
}

interface IndicatorsResponse {
  latest: Record<string, unknown>;
  series_tail: Record<string, IndicatorPoint[]>;
}

const EMA_DEFS = [
  { key: "ema20", label: "EMA 20", color: "#60a5fa" },
  { key: "ema50", label: "EMA 50", color: "#f59e0b" },
  { key: "ema200", label: "EMA 200", color: "#a78bfa" },
] as const;

export function GoldChart({ initialInterval = "1day" }: { initialInterval?: TimeframeInterval }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const emaRefs = useRef<Record<string, ISeriesApi<"Line">>>({});
  const [interval, setInterval_] = useState<TimeframeInterval>(initialInterval);
  const [count, setCount] = useState(0);
  const [lastTs, setLastTs] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showEma, setShowEma] = useState<Record<string, boolean>>({
    ema20: true,
    ema50: true,
    ema200: false,
  });
  const [latest, setLatest] = useState<IndicatorsResponse["latest"] | null>(null);

  // create chart once — but re-theme when [data-theme] changes (light/dark)
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const css = () => getComputedStyle(document.documentElement);
    const themeOpts = () => {
      const c = css();
      return {
        layout: {
          textColor: c.getPropertyValue("--chart-text").trim() || "#6d7480",
        },
        grid: {
          vertLines: { color: c.getPropertyValue("--chart-grid").trim() || "rgba(20,30,50,0.06)" },
          horzLines: { color: c.getPropertyValue("--chart-grid").trim() || "rgba(20,30,50,0.06)" },
        },
        timeScale: { borderColor: c.getPropertyValue("--line").trim() || "rgba(20,30,50,0.1)" },
        rightPriceScale: { borderColor: c.getPropertyValue("--line").trim() || "rgba(20,30,50,0.1)" },
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
        vertLines: { color: c.getPropertyValue("--chart-grid").trim() || "rgba(20,30,50,0.06)" },
        horzLines: { color: c.getPropertyValue("--chart-grid").trim() || "rgba(20,30,50,0.06)" },
      },
      width: el.clientWidth,
      height: 400,
      timeScale: { borderColor: c.getPropertyValue("--line").trim() || "rgba(20,30,50,0.1)", timeVisible: true },
      rightPriceScale: { borderColor: c.getPropertyValue("--line").trim() || "rgba(20,30,50,0.1)" },
      crosshair: {
        vertLine: { color: "rgba(199,143,10,0.4)", labelBackgroundColor: "#b8860b" },
        horzLine: { color: "rgba(199,143,10,0.4)", labelBackgroundColor: "#b8860b" },
      },
    });
    chart.applyOptions(themeOpts());
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: c.getPropertyValue("--chart-up").trim() || "#059669",
      downColor: c.getPropertyValue("--chart-down").trim() || "#e11d48",
      borderVisible: false,
      wickUpColor: c.getPropertyValue("--chart-up").trim() || "#059669",
      wickDownColor: c.getPropertyValue("--chart-down").trim() || "#e11d48",
    });
    chartRef.current = chart;
    candleRef.current = candles;
    for (const def of EMA_DEFS) {
      emaRefs.current[def.key] = chart.addSeries(LineSeries, {
        color: def.color,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
    }

    const observer = new ResizeObserver(() => {
      chart.applyOptions({ width: el.clientWidth });
    });
    observer.observe(el);
    // live re-theme on light/dark toggle
    const themeObserver = new MutationObserver(() => {
      chart.applyOptions(themeOpts());
    });
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => {
      observer.disconnect();
      themeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      emaRefs.current = {};
    };
  }, []);

  // load candles + indicator overlays per interval
  useEffect(() => {
    let cancelled = false;
    setError(null);
    Promise.all([
      fetch(`${API_URL}/api/v1/markets/XAUUSD/candles?interval=${interval}&limit=2000`).then((r) => {
        if (!r.ok) throw new Error(`candles API ${r.status}`);
        return r.json();
      }),
      fetch(`${API_URL}/api/v1/markets/XAUUSD/indicators?interval=${interval}`)
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null),
    ])
      .then(([candleData, indData]: [{ candles: Candle[] }, IndicatorsResponse | null]) => {
        if (cancelled || !candleRef.current) return;
        const bars = candleData.candles.map((c) => ({
          time: (new Date(c.market_ts).getTime() / 1000) as UTCTimestamp,
          open: Number(c.open),
          high: Number(c.high),
          low: Number(c.low),
          close: Number(c.close),
        }));
        candleRef.current.setData(bars);
        setCount(bars.length);
        setLastTs(candleData.candles.at(-1)?.market_ts ?? null);
        chartRef.current?.timeScale().fitContent();

        if (indData && indData.series_tail) {
          setLatest(indData.latest);
          for (const def of EMA_DEFS) {
            const points = indData.series_tail[def.key] ?? [];
            emaRefs.current[def.key]?.setData(
              points.map((p) => ({
                time: (new Date(p.time).getTime() / 1000) as UTCTimestamp,
                value: p.value,
              })),
            );
          }
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "failed to load chart data");
      });
    return () => {
      cancelled = true;
    };
  }, [interval]);

  // visibility toggles
  useEffect(() => {
    for (const def of EMA_DEFS) {
      emaRefs.current[def.key]?.applyOptions({ visible: showEma[def.key] ?? false });
    }
  }, [showEma]);

  return (
    <div className="card p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-baseline gap-3">
          <span className="text-[13.5px] font-semibold tracking-tight text-ink">XAU/USD</span>
          <span className="num text-[11px] text-faint">
            {count} candles{lastTs ? ` · last ${new Date(lastTs).toISOString().slice(0, 16)}Z` : ""}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-1">
          {EMA_DEFS.map((def) => (
            <button
              key={def.key}
              onClick={() => setShowEma((s) => ({ ...s, [def.key]: !s[def.key] }))}
              className={`rounded-md border px-2 py-1 text-[10.5px] font-medium transition-all ${showEma[def.key] ? "border-transparent text-[#0c0a03]" : "border-line text-muted hover:text-ink"}`}
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
                interval === tf.interval
                  ? "bg-gold-dim text-gold-bright"
                  : "text-muted hover:bg-white/5 hover:text-ink"
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
      <p className="mt-2.5 text-[10.5px] leading-relaxed text-faint">
        Charts render candles + indicators stored/computed in Postgres + quant engine (Twelve Data
        source). Newest candle may be provisional until it closes.
        {latest
          ? ` RSI(14) ${String(latest["rsi14"] ?? "—")} · ADX(14) ${String(latest["adx14"] ?? "—")} · ATR(14) ${String(latest["atr14"] ?? "—")}.`
          : ""}
      </p>
    </div>
  );
}
