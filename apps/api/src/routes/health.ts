import type { FastifyInstance } from "fastify";

interface DependencyStatus {
  status: "up" | "down" | "unconfigured";
  latencyMs?: number;
  error?: string;
}

async function checkTcpFetch(url: string, timeoutMs = 2000): Promise<DependencyStatus> {
  const start = performance.now();
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const res = await fetch(url, { signal: controller.signal });
    clearTimeout(timer);
    return { status: res.ok ? "up" : "down", latencyMs: Math.round(performance.now() - start) };
  } catch (err) {
    return { status: "down", latencyMs: Math.round(performance.now() - start), error: String(err) };
  }
}

async function checkPostgres(databaseUrl: string | undefined): Promise<DependencyStatus> {
  if (!databaseUrl) return { status: "unconfigured" };
  const start = performance.now();
  try {
    const { Client } = await import("pg");
    const client = new Client({ connectionString: databaseUrl, connectionTimeoutMillis: 2000 });
    await client.connect();
    await client.query("SELECT 1");
    await client.end();
    return { status: "up", latencyMs: Math.round(performance.now() - start) };
  } catch (err) {
    return { status: "down", latencyMs: Math.round(performance.now() - start), error: String(err) };
  }
}

async function checkRedis(redisUrl: string | undefined): Promise<DependencyStatus> {
  if (!redisUrl) return { status: "unconfigured" };
  const start = performance.now();
  try {
    const { Redis } = await import("ioredis");
    const redis = new Redis(redisUrl, { lazyConnect: true, connectTimeout: 2000, maxRetriesPerRequest: 1 });
    redis.on("error", () => {}); // suppress unhandled error events during probe
    await redis.connect();
    const pong = await redis.ping();
    await redis.quit();
    return { status: pong === "PONG" ? "up" : "down", latencyMs: Math.round(performance.now() - start) };
  } catch (err) {
    return { status: "down", latencyMs: Math.round(performance.now() - start), error: String(err) };
  }
}

export async function registerHealthRoutes(app: FastifyInstance): Promise<void> {
  // Liveness: process is running. Must not fail on dependency problems.
  app.get("/healthz", async () => ({
    status: "ok",
    service: "pmi-api",
    version: process.env.npm_package_version ?? "0.0.0",
    uptimeSec: Math.round(process.uptime()),
  }));

  // Readiness: critical dependencies reachable. 503 when any is down.
  app.get("/readyz", async (_request, reply) => {
    const [quant, postgres, redis] = await Promise.all([
      checkTcpFetch(`${app.config.quantInternalUrl}/health`),
      checkPostgres(app.config.databaseUrl),
      checkRedis(app.config.redisUrl),
    ]);

    const dependencies = { quant, postgres, redis };
    const allReady = Object.values(dependencies).every(
      (d) => d.status === "up" || d.status === "unconfigured",
    );

    reply.code(allReady ? 200 : 503);
    return { status: allReady ? "ready" : "degraded", dependencies };
  });
}
