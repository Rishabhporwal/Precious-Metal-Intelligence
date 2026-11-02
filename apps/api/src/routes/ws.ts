import type { FastifyInstance } from "fastify";
import type { WebSocket } from "ws";

interface QuotePayload {
  type: "quote";
  symbol: string;
  price: string | null;
  marketTs: string | null;
  receivedAt: string | null;
}

/**
 * /ws/markets — WebSocket fan-out of the latest stored quotes.
 *
 * The gateway owns no data logic: every tick is read from the quant engine
 * (which reads Postgres). Push interval is 5s; unchanged prices are not
 * re-pushed (dedup by price+ts).
 */
export async function registerWsRoutes(app: FastifyInstance): Promise<void> {
  app.get("/ws/markets", { websocket: true }, (socket: WebSocket) => {
    let lastSent = "";
    let closed = false;

    const push = async () => {
      if (closed || socket.readyState !== 1) return;
      try {
        const res = await fetch(`${app.config.quantInternalUrl}/v1/instruments/XAUUSD/quote`, {
          signal: AbortSignal.timeout(4000),
        });
        if (!res.ok) return;
        const body = (await res.json()) as {
          symbol: string;
          price: string;
          market_ts: string;
          received_at: string;
        };
        const payload: QuotePayload = {
          type: "quote",
          symbol: body.symbol,
          price: body.price,
          marketTs: body.market_ts,
          receivedAt: body.received_at,
        };
        const serialized = JSON.stringify(payload);
        if (serialized !== lastSent) {
          lastSent = serialized;
          socket.send(serialized);
        }
      } catch {
        // quant unreachable — stay silent, retry next tick
      }
    };

    void push();
    const timer = setInterval(() => void push(), 5000);

    socket.on("close", () => {
      closed = true;
      clearInterval(timer);
    });
    socket.on("error", () => {
      closed = true;
      clearInterval(timer);
    });
  });
}
