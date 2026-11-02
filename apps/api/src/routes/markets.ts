import type { FastifyInstance } from "fastify";
import type { ApiErrorResponse } from "@pmi/contracts";

const SYMBOL_RE = /^[A-Z]{3,8}$/;
const INTERVAL_RE = /^(1min|5min|15min|30min|1h|4h|1day|1week|1month)$/;

interface QuantError {
  detail?: string;
}

/** Proxy a request to the quant engine, mapping its errors honestly. */
async function proxy(
  app: FastifyInstance,
  path: string,
): Promise<{ statusCode: number; body: unknown }> {
  const base = app.config.quantInternalUrl;
  try {
    const res = await fetch(`${base}${path}`, {
      signal: AbortSignal.timeout(10_000),
    });
    const body = (await res.json().catch(() => null)) as unknown;
    if (!res.ok) {
      const detail = (body as QuantError | null)?.detail ?? `quant engine HTTP ${res.status}`;
      return { statusCode: res.status === 503 ? 503 : 502, body: { error: { code: "UPSTREAM_ERROR", message: detail } } satisfies ApiErrorResponse };
    }
    return { statusCode: res.status, body };
  } catch (err) {
    app.log.error({ err }, "quant engine unreachable");
    return {
      statusCode: 502,
      body: { error: { code: "UPSTREAM_UNREACHABLE", message: "quant engine unreachable" } } satisfies ApiErrorResponse,
    };
  }
}

export async function registerMarketRoutes(app: FastifyInstance): Promise<void> {
  app.get<{ Params: { symbol?: string }; Querystring: { interval?: string; limit?: string } }>(
    "/api/v1/markets/:symbol/candles",
    async (request, reply) => {
      const symbol = (request.params.symbol ?? "").toUpperCase();
      if (!SYMBOL_RE.test(symbol)) {
        return reply.code(400).send({
          error: { code: "INVALID_SYMBOL", message: "symbol must be 3-8 uppercase letters" },
        } satisfies ApiErrorResponse);
      }
      const interval = request.query.interval ?? "1day";
      if (!INTERVAL_RE.test(interval)) {
        return reply.code(400).send({
          error: { code: "INVALID_INTERVAL", message: "interval must be one of 1min,5min,15min,30min,1h,4h,1day,1week,1month" },
        } satisfies ApiErrorResponse);
      }
      const limit = Math.min(Math.max(parseInt(request.query.limit ?? "500", 10) || 500, 1), 5000);
      const result = await proxy(app, `/v1/instruments/${symbol}/candles?interval=${interval}&limit=${limit}`);
      return reply.code(result.statusCode).send(result.body);
    },
  );

  app.get<{ Params: { symbol?: string } }>("/api/v1/markets/:symbol/quote", async (request, reply) => {
    const symbol = (request.params.symbol ?? "").toUpperCase();
    if (!SYMBOL_RE.test(symbol)) {
      return reply.code(400).send({
        error: { code: "INVALID_SYMBOL", message: "symbol must be 3-8 uppercase letters" },
      } satisfies ApiErrorResponse);
    }
    const result = await proxy(app, `/v1/instruments/${symbol}/quote`);
    return reply.code(result.statusCode).send(result.body);
  });

  app.get("/api/v1/markets", async (_request, reply) => {
    const result = await proxy(app, "/v1/instruments");
    return reply.code(result.statusCode).send(result.body);
  });
}
