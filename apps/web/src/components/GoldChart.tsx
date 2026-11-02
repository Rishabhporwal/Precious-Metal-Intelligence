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

  // create chart once
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const chart = createChart(el, {
      layout: {
        background: { color: "transparent" },
        textColor: "#a3a3a3",
        fontFamily: "var(--font-geist-mono), monospace",
      },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.04)" },
        horzLines: { color: "rgba(255,255,255,0.04)" },
      },
      width: el.clientWidth,
      height: 380,
      timeScale: { borderColor: "#262626", timeVisible: true },
      rightPriceScale: { borderColor: "#262626" },
    });
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: "#34d399",
      downColor: "#f87171",
      borderVisible: false,
      wickUpColor: "#34d399",
      wickDownColor: "#f87171",
    });
    chartRef.current = chart;
    candleRef.current = candles;
    for (const def of EMA_DEFS) {
      emaRefs.current[def.key] = chart.addSeries(LineSeries, {
        color: def.color,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      });
    }

    const observer = new ResizeObserver(() => {
      chart.applyOptions({ width: el.clientWidth });
    });
    observer.observe(el);
    return () => {
      observer.disconnect();
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
    <div className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-baseline gap-3">
          <span className="text-sm font-medium text-neutral-100">XAU/USD</span>
          <span className="text-[11px] text-neutral-500">
            {count} candles{lastTs ? ` · last ${new Date(lastTs).toISOString().slice(0, 16)}Z` : ""}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-1">
          {EMA_DEFS.map((def) => (
            <button
              key={def.key}
              onClick={() => setShowEma((s) => ({ ...s, [def.key]: !s[def.key] }))}
              className={`rounded border px-2 py-1 font-mono text-[10px] transition-colors ${
                showEma[def.key]
                  ? "border-transparent text-neutral-900"
                  : "border-neutral-700 text-neutral-500"
              }`}
              style={showEma[def.key] ? { background: def.color } : {}}
            >
              {def.label}
            </button>
          ))}
          <span className="mx-1 text-neutral-700">|</span>
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf.interval}
              onClick={() => setInterval_(tf.interval)}
              className={`rounded px-2 py-1 font-mono text-[11px] transition-colors ${
                interval === tf.interval
                  ? "bg-neutral-100 text-neutral-900"
                  : "text-neutral-400 hover:bg-neutral-800 hover:text-neutral-200"
              }`}
            >
              {tf.label}
            </button>
          ))}
        </div>
      </div>
      {error ? (
        <p className="mt-4 text-xs text-red-400">Failed to load chart data: {error}</p>
      ) : (
        <div ref={containerRef} className="mt-3" />
      )}
      <p className="mt-2 text-[10px] text-neutral-600">
        Charts render candles + indicators stored/computed in Postgres + quant engine (Twelve Data
        source). Newest candle may be provisional until it closes.
        {latest
          ? ` RSI(14) ${String(latest["rsi14"] ?? "—")} · ADX(14) ${String(latest["adx14"] ?? "—")} · ATR(14) ${String(latest["atr14"] ?? "—")}.`
          : ""}
      </p>
    </div>
  );
}
