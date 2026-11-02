# API Documentation

All endpoints are versioned under `/api/v1` (Phase 1+). Phase 0 ships
infrastructure endpoints only.

## Phase 0 endpoints

### apps/api (Fastify, :8000)

| Method | Path       | Purpose      | Response                                            |
| ------ | ---------- | ------------ | --------------------------------------------------- |
| GET    | `/healthz` | Liveness     | `{status:"ok", service, version, uptimeSec}`        |
| GET    | `/readyz`  | Readiness    | `{status, dependencies:{quant,postgres,redis}}` — 503 when degraded |

### services/quant-engine (FastAPI, :8001)

| Method | Path     | Purpose   | Response                                            |
| ------ | -------- | --------- | ---------------------------------------------------- |
| GET    | `/health`| Liveness  | `{status, service, version}`                         |
| GET    | `/ready` | Readiness | `{status, dependencies:{postgres,redis}}` — 503 when degraded |

### apps/web (Next.js, :3100)

| Method | Path          | Purpose   | Response                                   |
| ------ | ------------- | --------- | ------------------------------------------ |
| GET    | `/api/health` | Liveness  | `{status:"ok", service, version, uptimeSec, timestamp}` |

## Planned endpoints (Phase 1+)

Full `/api/v1` surface per the master spec (markets, strategies, analysis,
setups, backtests, alerts, paper trading). Error envelope:

```json
{ "error": { "code": "NOT_FOUND", "message": "...", "details": {} } }
```

Shared TypeScript response contracts live in `packages/contracts`.
