import Fastify, { type FastifyInstance } from "fastify";
import cors from "@fastify/cors";
import websocket from "@fastify/websocket";
import { registerHealthRoutes } from "./routes/health.js";
import { registerMarketRoutes } from "./routes/markets.js";
import { registerWsRoutes } from "./routes/ws.js";
import { loadConfig, type AppConfig } from "./config.js";

export async function buildApp(config: AppConfig = loadConfig()): Promise<FastifyInstance> {
  const app = Fastify({
    logger: {
      level: config.logLevel,
      transport:
        config.nodeEnv === "production"
          ? undefined // structured JSON logs in production
          : { target: "pino-pretty", options: { translateTime: "HH:MM:ss Z", ignore: "pid,hostname" } },
    },
  });

  app.decorate("config", config);

  // Local-first app: the browser (localhost origins) talks to this gateway.
  await app.register(cors, {
    origin: [
      "http://localhost:3100",
      "http://127.0.0.1:3100",
      "http://localhost:3000",
      "http://127.0.0.1:3000",
    ],
  });
  await app.register(websocket);

  // Optional auth boundary (off by default for a local-first app).
  // When PMI_API_TOKEN is set, mutating methods must present `x-pmi-token`.
  app.addHook("onRequest", async (request, reply) => {
    if (!config.apiToken) return;
    const mutating = ["POST", "PATCH", "PUT", "DELETE"].includes(request.method);
    const exempt = request.url === "/healthz";
    if (mutating && !exempt && request.headers["x-pmi-token"] !== config.apiToken) {
      await reply.code(401).send({
        error: { code: "UNAUTHORIZED", message: "missing or invalid x-pmi-token header" },
      });
    }
  });

  registerHealthRoutes(app);
  registerMarketRoutes(app);
  registerWsRoutes(app);

  return app;
}

declare module "fastify" {
  interface FastifyInstance {
    config: AppConfig;
  }
}
