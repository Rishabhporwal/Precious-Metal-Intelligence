import { buildApp } from "./app.js";

const app = await buildApp();

const start = async (): Promise<void> => {
  try {
    await app.listen({ port: app.config.port, host: "0.0.0.0" });
  } catch (err) {
    app.log.error(err);
    process.exit(1);
  }
};

// Graceful shutdown
for (const signal of ["SIGINT", "SIGTERM"] as const) {
  process.on(signal, () => {
    void app.close().finally(() => process.exit(0));
  });
}

void start();
