"use client";

import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
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

export function GoldChart({ initialInterval = "1day" }: { initialInterval?: TimeframeInterval }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const [interval, setInterval_] = useState<TimeframeInterval>(initialInterval);
  const [count, setCount] = useState(0);
  const [lastTs, setLastTs] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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
    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#34d399",
      downColor: "#f87171",
      borderVisible: false,
      wickUpColor: "#34d399",
      wickDownColor: "#f87171",
    });
    chartRef.current = chart;
    seriesRef.current = series;

    const observer = new ResizeObserver(() => {
      chart.applyOptions({ width: el.clientWidth });
    });
    observer.observe(el);
    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  // load candles per interval
  useEffect(() => {
    let cancelled = false;
    setError(null);
    fetch(`${API_URL}/api/v1/markets/XAUUSD/candles?interval=${interval}&limit=2000`)
      .then((r) => {
        if (!r.ok) throw new Error(`API ${r.status}`);
        return r.json();
      })
      .then((data: { candles: Candle[] }) => {
        if (cancelled || !seriesRef.current) return;
        const bars: { time: UTCTimestamp; open: number; high: number; low: number; close: number }[] =
          data.candles.map((c) => ({
          time: (new Date(c.market_ts).getTime() / 1000) as UTCTimestamp,
          open: Number(c.open),
          high: Number(c.high),
          low: Number(c.low),
          close: Number(c.close),
        }));
        seriesRef.current.setData(bars);
        setCount(bars.length);
        setLastTs(data.candles.at(-1)?.market_ts ?? null);
        chartRef.current?.timeScale().fitContent();
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "failed to load candles");
      });
    return () => {
      cancelled = true;
    };
  }, [interval]);

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-baseline gap-3">
          <span className="text-sm font-medium text-neutral-100">XAU/USD</span>
          <span className="text-[11px] text-neutral-500">
            {count} candles{lastTs ? ` · last ${new Date(lastTs).toISOString().slice(0, 16)}Z` : ""}
          </span>
        </div>
        <div className="flex gap-1">
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
        <p className="mt-4 text-xs text-red-400">Failed to load candles: {error}</p>
      ) : (
        <div ref={containerRef} className="mt-3" />
      )}
      <p className="mt-2 text-[10px] text-neutral-600">
        Chart renders candles stored in Postgres (provider: Twelve Data). The newest candle may be
        provisional until it closes.
      </p>
    </div>
  );
}
