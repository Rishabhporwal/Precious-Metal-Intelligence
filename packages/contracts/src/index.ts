/**
 * Shared type contracts between web (Next.js), api (Fastify) and quant engine.
 *
 * Phase 0: service identity + health/readiness envelopes used by all three
 * services. Domain contracts (candles, detections, setups) arrive with the
 * phases that own them and are added here, never re-declared per service.
 */

export interface ServiceIdentity {
  status: "ok";
  service: string;
  version: string;
  uptimeSec: number;
}

export type DependencyState = "up" | "down" | "unconfigured";

export interface DependencyStatus {
  status: DependencyState;
  latencyMs?: number;
  error?: string;
}

export interface ReadinessResponse {
  status: "ready" | "degraded";
  dependencies: Record<string, DependencyStatus>;
}

export interface ApiError {
  code: string;
  message: string;
  details?: unknown;
}

/** Standard error envelope for v1 endpoints. */
export interface ApiErrorResponse {
  error: ApiError;
}
