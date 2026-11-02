import { describe, expect, it } from "vitest";

import { buildApp } from "../src/app.js";
import { loadConfig } from "../src/config.js";

describe("auth boundary", () => {
  it("allows all requests when no token configured (local-first default)", async () => {
    const app = await buildApp(loadConfig({}));
    const res = await app.inject({ method: "POST", url: "/api/v1/alerts", payload: {} });
    // gateway may 4xx/5xx from upstream, but NOT 401 from the boundary
    expect(res.statusCode).not.toBe(401);
    await app.close();
  });

  it("rejects mutating requests without the token when PMI_API_TOKEN is set", async () => {
    const app = await buildApp(loadConfig({ PMI_API_TOKEN: "secret1" }));
    const denied = await app.inject({ method: "POST", url: "/api/v1/alerts", payload: {} });
    expect(denied.statusCode).toBe(401);
    expect(denied.json().error.code).toBe("UNAUTHORIZED");

    const allowed = await app.inject({
      method: "POST",
      url: "/api/v1/alerts",
      headers: { "x-pmi-token": "secret1" },
      payload: {},
    });
    expect(allowed.statusCode).not.toBe(401);

    const health = await app.inject({ method: "GET", url: "/healthz" });
    expect(health.statusCode).toBe(200);
    await app.close();
  });
});
