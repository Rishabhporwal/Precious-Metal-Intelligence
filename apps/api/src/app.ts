import Fastify, { type FastifyInstance } from "fastify";
import { registerHealthRoutes } from "./routes/health.js";
import { registerMarketRoutes } from "./routes/markets.js";
import { loadConfig, type AppConfig } from "./config.js";

export function buildApp(config: AppConfig = loadConfig()): FastifyInstance {
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

  registerHealthRoutes(app);
  registerMarketRoutes(app);

  return app;
}

declare module "fastify" {
  interface FastifyInstance {
    config: AppConfig;
  }
}
