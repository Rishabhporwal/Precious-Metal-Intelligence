import type { DependencyStatus, ReadinessResponse, ServiceIdentity } from "@pmi/contracts";

export interface ServiceRow {
  id: string;
  label: string;
  port: string;
  status: "ok" | "degraded" | "down";
  detail: string;
  version: string | null;
  deps: { name: string; state: DependencyStatus["status"]; latencyMs?: number }[];
}

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";
const QUANT_INTERNAL_URL = process.env.QUANT_INTERNAL_URL ?? "http://localhost:8001";

async function getJson<T>(url: string): Promise<T | null> {
  try {
    const res = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(4000) });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

function depsToRows(deps: Record<string, DependencyStatus> | undefined) {
  if (!deps) return [];
  return Object.entries(deps).map(([name, d]) => ({ name, state: d.status, latencyMs: d.latencyMs }));
}

export async function getServiceRows(): Promise<ServiceRow[]> {
  const [apiHealth, apiReady, quantHealth, quantReady] = await Promise.all([
    getJson<ServiceIdentity & { status: string }>(`${API_INTERNAL_URL}/healthz`),
    getJson<ReadinessResponse>(`${API_INTERNAL_URL}/readyz`),
    getJson<{ status: string; service: string; version: string }>(`${QUANT_INTERNAL_URL}/health`),
    getJson<ReadinessResponse>(`${QUANT_INTERNAL_URL}/ready`),
  ]);

  const apiState = apiHealth ? (apiReady?.status === "ready" ? "ok" : "degraded") : "down";
  const quantState = quantHealth ? (quantReady?.status === "ready" ? "ok" : "degraded") : "down";

  return [
    {
      id: "web",
      label: "Web — Next.js",
      port: "3100",
      status: "ok",
      detail: "serving this page",
      version: "0.1.0",
      deps: [],
    },
    {
      id: "api",
      label: "API — Fastify",
      port: "8000",
      status: apiState,
      detail: apiHealth ? "liveness ok" : "unreachable",
      version: apiHealth?.version ?? null,
      deps: depsToRows(apiReady?.dependencies),
    },
    {
      id: "quant",
      label: "Quant Engine — FastAPI",
      port: "8001",
      status: quantState,
      detail: quantHealth ? "liveness ok" : "unreachable",
      version: quantHealth?.version ?? null,
      deps: depsToRows(quantReady?.dependencies),
    },
    {
      id: "postgres",
      label: "PostgreSQL + TimescaleDB",
      port: "5432",
      status:
        apiReady?.dependencies.postgres?.status === "up" ||
        quantReady?.dependencies.postgres?.status === "up"
          ? "ok"
          : "down",
      detail: "migration 0001_baseline applied",
      version: "pg16 / timescaledb 2.17.2",
      deps: [],
    },
    {
      id: "redis",
      label: "Redis",
      port: "6379",
      status:
        apiReady?.dependencies.redis?.status === "up" || quantReady?.dependencies.redis?.status === "up"
          ? "ok"
          : "down",
      detail: "cache + coordination",
      version: "7.4",
      deps: [],
    },
  ];
}
