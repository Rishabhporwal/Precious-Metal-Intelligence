# Local Setup

## Prerequisites

- Docker Desktop (or compatible engine) running
- Node >= 22 + pnpm 10 (`corepack enable`)
- Python 3.12+ and [uv](https://docs.astral.sh/uv/)

## First run

```bash
cp .env.example .env      # edit values (passwords, provider keys)
docker compose up -d --build
```

## Verify the stack

```bash
docker compose ps                                    # all services Up (healthy)
curl -s localhost:8000/healthz | jq                  # api liveness
curl -s localhost:8000/readyz | jq                   # api readiness (quant/pg/redis)
curl -s localhost:8001/health | jq                   # quant liveness
curl -s localhost:8001/ready | jq                    # quant readiness
curl -s localhost:3100/api/health | jq               # web health
docker exec pmi-postgres psql -U pmi -d pmi -c "SELECT * FROM platform_metadata;"
docker exec pmi-redis redis-cli ping                 # PONG
```

## Run migrations

```bash
export DATABASE_URL_HOST="postgresql://pmi:<password>@localhost:5432/pmi"
pnpm migrate          # alembic upgrade head (uses quant-engine venv)
```

## Local dev (hot reload, no docker for app services)

```bash
docker compose up -d postgres redis
pnpm dev:api          # Fastify  :8000
pnpm dev:quant        # FastAPI  :8001
pnpm dev:web          # Next.js  :3100
```

## Reset

```bash
docker compose down -v     # destroys volumes (postgres + redis data)
```

## Troubleshooting

| Symptom                                  | Fix                                                        |
| ---------------------------------------- | ---------------------------------------------------------- |
| `docker compose up` fails on port 5432/6379 | Another local pg/redis is bound; stop it or override ports in `.env` |
| web unreachable on 3000                  | Intentional — web is on **3100** (see ADR-0002)             |
| `/readyz` reports quant `down`           | quant container not healthy yet; `docker compose logs quant` |
