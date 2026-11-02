"use client";

import { useEffect, useState } from "react";

interface QuoteMessage {
  type: "quote";
  symbol: string;
  price: string | null;
  marketTs: string | null;
  receivedAt: string | null;
}

const WS_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /^http/,
  "ws",
);

/** Live gold price over the gateway WebSocket, with auto-reconnect. */
export function LiveTicker() {
  const [quote, setQuote] = useState<QuoteMessage | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    let retryMs = 2000;

    const connect = () => {
      if (closed) return;
      ws = new WebSocket(`${WS_URL}/ws/markets`);
      ws.onopen = () => {
        setConnected(true);
        retryMs = 2000;
      };
      ws.onmessage = (ev) => {
        try {
          setQuote(JSON.parse(ev.data as string) as QuoteMessage);
        } catch {
          // ignore malformed frames
        }
      };
      ws.onclose = () => {
        setConnected(false);
        if (!closed) {
          setTimeout(connect, retryMs);
          retryMs = Math.min(retryMs * 2, 30000);
        }
      };
      ws.onerror = () => ws?.close();
    };
    connect();
    return () => {
      closed = true;
      ws?.close();
    };
  }, []);

  const price = quote?.price ? Number(quote.price) : null;
  const formatted =
    price != null
      ? price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
      : null;

  return (
    <div className="rounded-lg border border-yellow-900/50 bg-neutral-900/60 p-5">
      <div className="flex items-center justify-between">
        <div className="text-xs text-neutral-400">Gold — XAU/USD (spot)</div>
        <div className="flex items-center gap-1.5 font-mono text-[10px] text-neutral-500">
          <span
            className={`inline-block h-1.5 w-1.5 rounded-full ${
              connected ? "animate-pulse bg-emerald-400" : "bg-neutral-600"
            }`}
          />
          {connected ? "WS LIVE" : "WS OFFLINE"}
        </div>
      </div>
      <div className="mt-2 flex items-baseline gap-3">
        <span className="font-mono text-5xl font-semibold text-neutral-100">
          {formatted ?? "—"}
        </span>
        {quote?.marketTs && (
          <span className="font-mono text-[11px] text-neutral-500">
            mkt {new Date(quote.marketTs).toISOString().slice(5, 16)}Z
          </span>
        )}
      </div>
      <p className="mt-2 font-mono text-[10px] text-neutral-600">
        streamed from stored quotes (ingestion refreshes every 5 min) · not financial advice
      </p>
    </div>
  );
}
