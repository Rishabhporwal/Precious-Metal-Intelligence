import { describe, it, expect, beforeAll, afterAll } from "vitest";
import type { FastifyInstance } from "fastify";
import { buildApp } from "../src/app.js";

let app: FastifyInstance;

beforeAll(async () => {
  app = await buildApp({
    port: 0,
    nodeEnv: "test",
    logLevel: "silent",
    databaseUrl: undefined,
    redisUrl: undefined,
    quantInternalUrl: "http://localhost:1", // unreachable on purpose
  });
});

afterAll(async () => {
  await app.close();
});

describe("GET /healthz", () => {
  it("returns 200 with service metadata", async () => {
    const res = await app.inject({ method: "GET", url: "/healthz" });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.status).toBe("ok");
    expect(body.service).toBe("pmi-api");
    expect(typeof body.uptimeSec).toBe("number");
  });
});

describe("GET /readyz", () => {
  it("reports degraded when quant is unreachable but unconfigured deps pass", async () => {
    const res = await app.inject({ method: "GET", url: "/readyz" });
    expect(res.statusCode).toBe(503);
    const body = res.json();
    expect(body.status).toBe("degraded");
    expect(body.dependencies.quant.status).toBe("down");
    expect(body.dependencies.postgres.status).toBe("unconfigured");
    expect(body.dependencies.redis.status).toBe("unconfigured");
  });
});
