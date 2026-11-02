# ADR-0001: Monorepo layout and service boundaries

**Status:** Accepted (2026-11-02)

## Decision

pnpm workspace monorepo as specified by the master spec:

- `apps/web` — Next.js 16 UI (presentation only)
- `apps/api` — Fastify 5 gateway (validation, auth boundary, WS fan-out)
- `services/quant-engine` — Python FastAPI (all numerical work: indicators,
  strategies, risk, backtesting, LangGraph)
- `packages/contracts` — shared TS types; single source of API envelopes
- `database/` — Alembic migrations + seeds + scripts
- `infrastructure/docker` — service images; compose file at repo root

## Rationale

- Quant logic centralized in Python: testable, deterministic, backend-owned.
- Fastify stays a thin gateway — no business/quant logic in controllers.
- Contracts package prevents response-shape drift between web and api.

## Consequences

- web → api → quant dependency chain; quant is the only service allowed to
  touch pandas/num models.
- Alembic is run through the quant-engine venv (`pnpm migrate`) but migrations
  live centrally under `database/migrations/`.
