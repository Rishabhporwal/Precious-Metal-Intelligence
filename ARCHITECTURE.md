# Architecture

## Service topology

```
┌──────────┐   REST/WS   ┌──────────┐   internal HTTP   ┌───────────────┐
│  apps/web │ ──────────> │ apps/api │ ────────────────> │ quant-engine  │
│ (Next.js) │             (Fastify)   │                   │ (FastAPI, Py) │
└──────────┘              └────┬─────┘                   └───────┬───────┘
                               │                                  │
                        ┌──────┴──────────────────────────────────┴──────┐
                        │        postgres (TimescaleDB)   +   redis      │
                        └────────────────────────────────────────────────┘
```

## Responsibilities

| Component     | Owns                                                                 |
| ------------- | -------------------------------------------------------------------- |
| `apps/web`    | Presentation only. Fetches from `/api/v1/*`. No calculations.        |
| `apps/api`    | REST gateway, request validation, auth boundary, orchestration of quant calls, WebSocket fan-out. No quant logic. |
| `quant-engine`| Indicators, strategy detection (SMC/ICT/Wyckoff/…), confluence, risk math, backtesting, LangGraph AI orchestration. |
| `postgres`    | System of record. NUMERIC for financial values, UTC timestamps, provider observations preserved. |
| `redis`       | Cache, rate-limit coordination, lightweight pub/sub. Never the source of truth. |

## Non-negotiable rules

1. LLMs never produce numerical market levels (entries/stops/targets/prices) —
   these come exclusively from deterministic Python outputs; the AI analyst
   narrates and structures evidence only.
2. Retrieved news/macro content is untrusted input; parsing is isolated and
   validated before use (prompt-injection defense).
3. Provider observations are preserved raw; canonical candles are derived and
   quality-flagged. Spot tick volume is never labelled as exchange volume.
4. Historical analysis is append-only — never overwritten.
5. All timestamps stored in UTC; display-timezone conversion happens at the edge.

## ADRs

Architectural decisions are recorded in `docs/adr/`. Phase 0 decisions:
- ADR-0001: monorepo layout and service boundaries (this document).
- ADR-0002: web port 3100 (dev-port collision with operator's Research Platform).
