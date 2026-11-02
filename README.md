# Precious Metals Intelligence (PMI)

AI-powered Gold & Silver market intelligence platform: real market data, technical
analysis, Smart Money Concepts / ICT / Wyckoff strategy detection, macro & news
intelligence, evidence-backed AI analysis, risk-validated trade setups, paper
trading and reproducible backtesting.

> **Status:** Phase 0 (platform bootstrap) complete — see
> [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md).

## Architecture

Three independent services behind a versioned REST API:

```
Browser ──> apps/web (Next.js, :3100) ──> apps/api (Fastify, :8000) ──> services/quant-engine (FastAPI, :8001)
                                                │                                   │
                                                └──────── postgres (TimescaleDB, :5432) + redis (:6379) ──────────┘
```

- **No quantitative calculations** live in the web app or Fastify controllers —
  the Python quant engine owns all numerical work.
- **PostgreSQL/TimescaleDB** is the system of record; **Redis** is cache/coordination only.
- See [ARCHITECTURE.md](ARCHITECTURE.md).

## Quick start (Docker)

```bash
cp .env.example .env          # fill in provider keys when you have them
docker compose up -d --build
```

| Service         | URL                          | Health endpoint        |
| --------------- | ---------------------------- | ---------------------- |
| Web (Next.js)   | http://localhost:3100        | `/api/health`          |
| API (Fastify)   | http://localhost:8000        | `/healthz`, `/readyz`  |
| Quant (FastAPI) | http://localhost:8001        | `/health`, `/ready`    |
| PostgreSQL      | localhost:5432 (`pmi` db)    | `pg_isready`           |
| Redis           | localhost:6379               | `redis-cli ping`       |

> **Port note:** web runs on **3100**, not 3000 — 3000 is reserved by the
> operator's other local dev server (Research Platform).

## Local development (without Docker)

```bash
pnpm install                          # workspace deps (Node >= 22, pnpm 10)
cd services/quant-engine && uv sync   # Python 3.12+ via uv

pnpm dev:web      # Next.js on :3100
pnpm dev:api      # Fastify on :8000
pnpm dev:quant    # FastAPI on :8001

docker compose up -d postgres redis   # infra only
pnpm migrate                          # run Alembic migrations (needs DATABASE_URL_HOST)
```

## Tests

```bash
pnpm test            # JS workspaces (vitest)
pnpm test:quant      # quant engine (pytest) + ruff lint
```

## Repository layout

```
apps/web          Next.js 16 trading terminal UI
apps/api          Fastify REST API gateway (:8000)
services/quant-engine   Python FastAPI quant engine (:8001) — indicators,
                        strategies, backtesting, LangGraph orchestration
packages/contracts      shared type contracts (TS)
database/         Alembic migrations, seeds, scripts
infrastructure/   Dockerfiles, (compose at repo root)
docs/             architecture, ADRs, API, data dictionary, runbooks
```

## Credentials required (Phase 1+)

| Provider      | Env var               | Used for                       |
| ------------- | --------------------- | ------------------------------ |
| Twelve Data   | `TWELVEDATA_API_KEY`  | market data (quotes/candles)   |
| FRED          | `FRED_API_KEY`        | macro time series              |
| News/calendar | `NEWS_API_KEY`, …     | news + economic events (Ph. 5) |
| LLM           | `LLM_API_KEY`, …      | AI analyst (Phase 7)           |
| Telegram      | `TELEGRAM_BOT_TOKEN`  | alerts (Phase 8)               |

Missing credentials never cause mock data to be substituted — integrations
report their status honestly instead.
