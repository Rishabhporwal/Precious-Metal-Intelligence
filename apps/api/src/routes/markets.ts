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

  app.get<{ Params: { symbol?: string }; Querystring: { interval?: string; limit?: string } }>(
    "/api/v1/markets/:symbol/indicators",
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
          error: { code: "INVALID_INTERVAL", message: "invalid interval" },
        } satisfies ApiErrorResponse);
      }
      const result = await proxy(app, `/v1/instruments/${symbol}/indicators?interval=${interval}`);
      return reply.code(result.statusCode).send(result.body);
    },
  );

  app.get<{ Params: { symbol?: string }; Querystring: { interval?: string } }>(
    "/api/v1/markets/:symbol/structure",
    async (request, reply) => {
      const symbol = (request.params.symbol ?? "").toUpperCase();
      if (!SYMBOL_RE.test(symbol)) {
        return reply.code(400).send({
          error: { code: "INVALID_SYMBOL", message: "symbol must be 3-8 uppercase letters" },
        } satisfies ApiErrorResponse);
      }
      const interval = request.query.interval ?? "1h";
      if (!INTERVAL_RE.test(interval)) {
        return reply.code(400).send({
          error: { code: "INVALID_INTERVAL", message: "invalid interval" },
        } satisfies ApiErrorResponse);
      }
      const result = await proxy(app, `/v1/instruments/${symbol}/structure?interval=${interval}`);
      return reply.code(result.statusCode).send(result.body);
    },
  );

  app.get<{ Params: { symbol?: string } }>(
    "/api/v1/markets/:symbol/quant",
    async (request, reply) => {
      const symbol = (request.params.symbol ?? "").toUpperCase();
      if (!SYMBOL_RE.test(symbol)) {
        return reply.code(400).send({
          error: { code: "INVALID_SYMBOL", message: "symbol must be 3-8 uppercase letters" },
        } satisfies ApiErrorResponse);
      }
      const result = await proxy(app, `/v1/instruments/${symbol}/quant`);
      return reply.code(result.statusCode).send(result.body);
    },
  );

  app.get("/api/v1/strategies", async (_request, reply) => {
    const result = await proxy(app, "/v1/strategies");
    return reply.code(result.statusCode).send(result.body);
  });

  app.get<{ Querystring: { symbol?: string; interval?: string; limit?: string } }>(
    "/api/v1/strategies/detections",
    async (request, reply) => {
      const symbol = (request.query.symbol ?? "XAUUSD").toUpperCase();
      if (!SYMBOL_RE.test(symbol)) {
        return reply.code(400).send({
          error: { code: "INVALID_SYMBOL", message: "symbol must be 3-8 uppercase letters" },
        } satisfies ApiErrorResponse);
      }
      const interval = request.query.interval;
      if (interval && !INTERVAL_RE.test(interval)) {
        return reply.code(400).send({
          error: { code: "INVALID_INTERVAL", message: "invalid interval" },
        } satisfies ApiErrorResponse);
      }
      const limit = Math.min(Math.max(parseInt(request.query.limit ?? "50", 10) || 50, 1), 200);
      const q = `/v1/strategies/detections?symbol=${symbol}${interval ? `&interval=${interval}` : ""}&limit=${limit}`;
      const result = await proxy(app, q);
      return reply.code(result.statusCode).send(result.body);
    },
  );

  app.get("/api/v1/macro/summary", async (_request, reply) => {
    const result = await proxy(app, "/v1/macro/summary");
    return reply.code(result.statusCode).send(result.body);
  });

  app.get<{ Querystring: { days_ahead?: string } }>("/api/v1/macro/events", async (request, reply) => {
    const days = Math.min(Math.max(parseInt(request.query.days_ahead ?? "30", 10) || 30, 1), 180);
    const result = await proxy(app, `/v1/macro/events?days_ahead=${days}`);
    return reply.code(result.statusCode).send(result.body);
  });

  app.get("/api/v1/macro/news", async (_request, reply) => {
    const result = await proxy(app, "/v1/macro/news?limit=20");
    return reply.code(result.statusCode).send(result.body);
  });

  app.post("/api/v1/analysis/generate", async (request, reply) => {
    try {
      const body = (request.body ?? {}) as { symbol?: string; interval?: string };
      const symbol = (body.symbol ?? "XAUUSD").toUpperCase();
      if (!SYMBOL_RE.test(symbol)) {
        return reply.code(400).send({
          error: { code: "INVALID_SYMBOL", message: "symbol must be 3-8 uppercase letters" },
        } satisfies ApiErrorResponse);
      }
      const res = await fetch(`${app.config.quantInternalUrl}/v1/analysis/generate`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ symbol, interval: body.interval ?? "1day" }),
        signal: AbortSignal.timeout(120000),
      });
      const payload = await res.json().catch(() => null);
      return reply.code(res.ok ? 200 : res.status).send(payload);
    } catch (err) {
      app.log.error({ err }, "analysis generation failed");
      return reply.code(502).send({
        error: { code: "UPSTREAM_ERROR", message: "analysis generation failed" },
      } satisfies ApiErrorResponse);
    }
  });

  app.get<{ Params: { symbol?: string } }>("/api/v1/analysis/latest/:symbol", async (request, reply) => {
    const symbol = (request.params.symbol ?? "").toUpperCase();
    if (!SYMBOL_RE.test(symbol)) {
      return reply.code(400).send({
        error: { code: "INVALID_SYMBOL", message: "symbol must be 3-8 uppercase letters" },
      } satisfies ApiErrorResponse);
    }
    const result = await proxy(app, `/v1/analysis/latest/${symbol}`);
    return reply.code(result.statusCode).send(result.body);
  });

  app.get<{ Params: { symbol?: string } }>("/api/v1/analysis/history/:symbol", async (request, reply) => {
    const symbol = (request.params.symbol ?? "").toUpperCase();
    if (!SYMBOL_RE.test(symbol)) {
      return reply.code(400).send({
        error: { code: "INVALID_SYMBOL", message: "symbol must be 3-8 uppercase letters" },
      } satisfies ApiErrorResponse);
    }
    const result = await proxy(app, `/v1/analysis/history/${symbol}`);
    return reply.code(result.statusCode).send(result.body);
  });

  app.get("/api/v1/setups", async (_request, reply) => {
    const result = await proxy(app, "/v1/setups");
    return reply.code(result.statusCode).send(result.body);
  });

  app.post<{ Querystring: { symbol?: string; interval?: string } }>(
    "/api/v1/strategies/evaluate_setups",
    async (request, reply) => {
      const symbol = ((request.query.symbol as string) ?? "XAUUSD").toUpperCase();
      if (!SYMBOL_RE.test(symbol)) {
        return reply.code(400).send({
          error: { code: "INVALID_SYMBOL", message: "symbol must be 3-8 uppercase letters" },
        } satisfies ApiErrorResponse);
      }
      const res = await fetch(
        `${app.config.quantInternalUrl}/v1/strategies/evaluate_setups?symbol=${symbol}&interval=${request.query.interval ?? "1h"}`,
        { method: "POST", signal: AbortSignal.timeout(60000) },
      );
      const payload = await res.json().catch(() => null);
      return reply.code(res.ok ? 200 : res.status).send(payload);
    },
  );

  app.get("/api/v1/alerts", async (_request, reply) => {
    const result = await proxy(app, "/v1/alerts");
    return reply.code(result.statusCode).send(result.body);
  });

  app.post("/api/v1/alerts", async (request, reply) => {
    const res = await fetch(`${app.config.quantInternalUrl}/v1/alerts`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(request.body ?? {}),
      signal: AbortSignal.timeout(15000),
    });
    const payload = await res.json().catch(() => null);
    return reply.code(res.ok ? 200 : res.status).send(payload);
  });

  app.delete<{ Params: { id?: string } }>("/api/v1/alerts/:id", async (request, reply) => {
    const result = await proxy(app, `/v1/alerts/${request.params.id}`);
    return reply.code(result.statusCode).send(result.body);
  });

  app.post("/api/v1/alerts/evaluate", async (_request, reply) => {
    const res = await fetch(`${app.config.quantInternalUrl}/v1/alerts/evaluate`, {
      method: "POST",
      signal: AbortSignal.timeout(30000),
    });
    const payload = await res.json().catch(() => null);
    return reply.code(res.ok ? 200 : res.status).send(payload);
  });

  app.get("/api/v1/paper/accounts", async (_request, reply) => {
    const result = await proxy(app, "/v1/paper/accounts");
    return reply.code(result.statusCode).send(result.body);
  });

  app.post("/api/v1/paper/trades", async (request, reply) => {
    const res = await fetch(`${app.config.quantInternalUrl}/v1/paper/trades`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(request.body ?? {}),
      signal: AbortSignal.timeout(15000),
    });
    const payload = await res.json().catch(() => null);
    return reply.code(res.ok ? 200 : res.status).send(payload);
  });

  app.get<{ Querystring: { status?: string } }>("/api/v1/paper/trades", async (request, reply) => {
    const result = await proxy(app, `/v1/paper/trades?status=${request.query.status ?? "all"}`);
    return reply.code(result.statusCode).send(result.body);
  });

  app.post<{ Params: { id?: string }; Querystring: { reason?: string } }>(
    "/api/v1/paper/trades/:id/close",
    async (request, reply) => {
      const id = parseInt(request.params.id ?? "0", 10);
      if (!Number.isInteger(id) || id <= 0) {
        return reply.code(400).send({
          error: { code: "INVALID_ID", message: "trade id must be a positive integer" },
        } satisfies ApiErrorResponse);
      }
      const res = await fetch(
        `${app.config.quantInternalUrl}/v1/paper/trades/${id}/close?reason=${request.query.reason ?? "manual"}`,
        { method: "POST", signal: AbortSignal.timeout(15000) },
      );
      const payload = await res.json().catch(() => null);
      return reply.code(res.ok ? 200 : res.status).send(payload);
    },
  );

  app.post("/api/v1/paper/monitor", async (_request, reply) => {
    const res = await fetch(`${app.config.quantInternalUrl}/v1/paper/monitor`, {
      method: "POST",
      signal: AbortSignal.timeout(30000),
    });
    const payload = await res.json().catch(() => null);
    return reply.code(res.ok ? 200 : res.status).send(payload);
  });

  app.get<{ Querystring: { symbol?: string } }>("/api/v1/verdict/latest", async (request, reply) => {
    const symbol = ((request.query.symbol as string) ?? "XAUUSD").toUpperCase();
    if (!SYMBOL_RE.test(symbol)) {
      return reply.code(400).send({
        error: { code: "INVALID_SYMBOL", message: "symbol must be 3-8 uppercase letters" },
      } satisfies ApiErrorResponse);
    }
    const result = await proxy(app, `/v1/verdict/latest?symbol=${symbol}`);
    return reply.code(result.statusCode).send(result.body);
  });

  app.get<{ Querystring: { symbol?: string; interval?: string } }>(
    "/api/v1/strategy-verdicts/latest",
    async (request, reply) => {
      const symbol = ((request.query.symbol as string) ?? "XAUUSD").toUpperCase();
      const interval = ((request.query.interval as string) ?? "1h").toLowerCase();
      if (!SYMBOL_RE.test(symbol) || !INTERVAL_RE.test(interval)) {
        return reply.code(400).send({
          error: { code: "INVALID_PARAMS", message: "invalid symbol or interval" },
        } satisfies ApiErrorResponse);
      }
      const result = await proxy(app, `/v1/strategy-verdicts/latest?symbol=${symbol}&interval=${interval}`);
      return reply.code(result.statusCode).send(result.body);
    },
  );

  app.post("/api/v1/verdict/generate", async (request, reply) => {
    try {
      const q = (request.query as { symbol?: string })?.symbol ?? "XAUUSD";
      const res = await fetch(
        `${app.config.quantInternalUrl}/v1/verdict/generate?symbol=${encodeURIComponent(q.toUpperCase())}`,
        { method: "POST", signal: AbortSignal.timeout(600000) },
      );
      const payload = await res.json().catch(() => null);
      return reply.code(res.ok ? 200 : res.status).send(payload);
    } catch (err) {
      app.log.error({ err }, "verdict generation failed");
      return reply.code(502).send({
        error: { code: "UPSTREAM_ERROR", message: "verdict generation failed" },
      } satisfies ApiErrorResponse);
    }
  });

  app.get<{ Querystring: { symbol?: string } }>("/api/v1/data/quality", async (request, reply) => {
    const symbol = ((request.query.symbol as string) ?? "XAUUSD").toUpperCase();
    if (!SYMBOL_RE.test(symbol)) {
      return reply.code(400).send({
        error: { code: "INVALID_SYMBOL", message: "symbol must be 3-8 uppercase letters" },
      } satisfies ApiErrorResponse);
    }
    const result = await proxy(app, `/v1/data/quality?symbol=${symbol}`);
    return reply.code(result.statusCode).send(result.body);
  });

  app.post("/api/v1/backtests", async (request, reply) => {
    try {
      const res = await fetch(`${app.config.quantInternalUrl}/v1/backtests`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(request.body ?? {}),
        signal: AbortSignal.timeout(300000),
      });
      const payload = await res.json().catch(() => null);
      return reply.code(res.ok ? 200 : res.status).send(payload);
    } catch (err) {
      app.log.error({ err }, "backtest failed");
      return reply.code(502).send({
        error: { code: "UPSTREAM_ERROR", message: "backtest failed" },
      } satisfies ApiErrorResponse);
    }
  });

  app.get<{ Querystring: { symbol?: string } }>("/api/v1/backtests", async (request, reply) => {
    const symbol = ((request.query.symbol as string) ?? "XAUUSD").toUpperCase();
    if (!SYMBOL_RE.test(symbol)) {
      return reply.code(400).send({
        error: { code: "INVALID_SYMBOL", message: "symbol must be 3-8 uppercase letters" },
      } satisfies ApiErrorResponse);
    }
    const result = await proxy(app, `/v1/backtests?symbol=${symbol}`);
    return reply.code(result.statusCode).send(result.body);
  });

  app.get<{ Params: { id?: string } }>("/api/v1/backtests/:id", async (request, reply) => {
    const id = parseInt(request.params.id ?? "0", 10);
    if (!Number.isInteger(id) || id <= 0) {
      return reply.code(400).send({
        error: { code: "INVALID_ID", message: "run id must be a positive integer" },
      } satisfies ApiErrorResponse);
    }
    const result = await proxy(app, `/v1/backtests/${id}`);
    return reply.code(result.statusCode).send(result.body);
  });

  app.post("/api/v1/strategies/evaluate", async (request, reply) => {
    try {
      const body = (request.body ?? {}) as { symbol?: string; intervals?: string[] };
      const symbol = (body.symbol ?? "XAUUSD").toUpperCase();
      if (!SYMBOL_RE.test(symbol)) {
        return reply.code(400).send({
          error: { code: "INVALID_SYMBOL", message: "symbol must be 3-8 uppercase letters" },
        } satisfies ApiErrorResponse);
      }
      const intervals = (body.intervals ?? ["15min", "1h", "1day"]).filter((i) =>
        INTERVAL_RE.test(i),
      );
      const res = await fetch(`${app.config.quantInternalUrl}/v1/strategies/evaluate`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ symbol, intervals }),
        signal: AbortSignal.timeout(60000),
      });
      const payload = await res.json().catch(() => null);
      return reply.code(res.ok ? 200 : res.status).send(payload);
    } catch (err) {
      app.log.error({ err }, "strategy evaluation failed");
      return reply.code(502).send({
        error: { code: "UPSTREAM_ERROR", message: "strategy evaluation failed" },
      } satisfies ApiErrorResponse);
    }
  });
}
