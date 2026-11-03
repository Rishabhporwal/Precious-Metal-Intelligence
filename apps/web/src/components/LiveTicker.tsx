"use client";

import { useEffect, useRef, useState } from "react";

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
  const [direction, setDirection] = useState<"up" | "down" | null>(null);
  const prevRef = useRef<number | null>(null);
  const dirTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

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
          const msg = JSON.parse(ev.data as string) as QuoteMessage;
          setQuote(msg);
          const p = msg.price ? Number(msg.price) : null;
          if (p != null && prevRef.current != null && p !== prevRef.current) {
            setDirection(p > prevRef.current ? "up" : "down");
            if (dirTimer.current) clearTimeout(dirTimer.current);
            dirTimer.current = setTimeout(() => setDirection(null), 2500);
          }
          if (p != null) prevRef.current = p;
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
      if (dirTimer.current) clearTimeout(dirTimer.current);
      ws?.close();
    };
  }, []);

  const price = quote?.price ? Number(quote.price) : null;
  const formatted =
    price != null
      ? price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
      : null;

  return (
    <div className="card relative overflow-hidden rise">
      {/* gold sheen accent */}
      <div
        aria-hidden
        className="pointer-events-none absolute -top-24 right-0 h-56 w-72 rounded-full opacity-[0.07]"
        style={{
          background: "radial-gradient(circle at center, #e6b422 0%, transparent 65%)",
        }}
      />
      <div className="relative flex items-start justify-between p-6 pb-0">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[13px] font-medium text-ink-soft">Gold</span>
            <span className="pill text-[10px] text-faint">XAU/USD · spot</span>
          </div>
          <div className="mt-3 flex items-baseline gap-3">
            <span
              className={`metric-xl text-[56px] transition-colors duration-500 ${
                direction === "up"
                  ? "text-up"
                  : direction === "down"
                    ? "text-down"
                    : "text-ink"
              }`}
            >
              {formatted ?? "—"}
            </span>
            {direction && (
              <span
                className={`text-lg ${direction === "up" ? "text-up" : "text-down"}`}
                aria-hidden
              >
                {direction === "up" ? "▲" : "▼"}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1.5 text-[10.5px] font-medium text-faint">
          <span className={`dot ${connected ? "dot-live" : "bg-faint"}`} />
          {connected ? "LIVE" : "OFFLINE"}
        </div>
      </div>
      <div className="relative flex items-center gap-3 px-6 pb-5 pt-2">
        {quote?.marketTs && (
          <span className="num text-[11px] text-faint">
            mkt {new Date(quote.marketTs).toISOString().slice(5, 16)}Z
          </span>
        )}
        <span className="text-[10.5px] text-faint">
          streamed from stored quotes · not financial advice
        </span>
      </div>
    </div>
  );
}
