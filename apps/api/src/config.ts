export interface AppConfig {
  port: number;
  nodeEnv: string;
  logLevel: string;
  databaseUrl: string | undefined;
  redisUrl: string | undefined;
  quantInternalUrl: string;
  /** Optional shared token: when set, mutating requests must carry header `x-pmi-token`. */
  apiToken: string | undefined;
}

function requireInt(env: NodeJS.ProcessEnv, key: string, fallback: number): number {
  const raw = env[key];
  if (raw === undefined || raw === "") return fallback;
  const n = Number(raw);
  if (!Number.isInteger(n) || n <= 0) {
    throw new Error(`Invalid environment configuration: ${key} must be a positive integer, got "${raw}"`);
  }
  return n;
}

/**
 * Application configuration. Read once at startup; no business logic here.
 * Fails fast on invalid values. DATABASE_URL / REDIS_URL are optional in
 * Phase 0 so the API can boot before the data layer lands in Phase 1.
 */
export function loadConfig(env: NodeJS.ProcessEnv = process.env): AppConfig {
  return {
    port: requireInt(env, "PORT", 8000),
    nodeEnv: env.NODE_ENV ?? "development",
    logLevel: env.LOG_LEVEL ?? "info",
    databaseUrl: env.DATABASE_URL || undefined,
    redisUrl: env.REDIS_URL || undefined,
    quantInternalUrl: env.QUANT_INTERNAL_URL || "http://localhost:8001",
    apiToken: env.PMI_API_TOKEN || undefined,
  };
}
