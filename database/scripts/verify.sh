#!/usr/bin/env bash
# PMI full verification: unit tests, lint, type checks, live health.
# Run from the repo root: ./scripts/verify.sh  (bash database/scripts/verify.sh also fine)
set -euo pipefail
cd "$(dirname "$0")/../.."

echo "== python: ruff =="
(cd services/quant-engine && uv run ruff check .)

echo "== python: pytest =="
(cd services/quant-engine && uv run pytest -q)

echo "== api: vitest + tsc =="
(cd apps/api && pnpm exec tsc -p tsconfig.json --noEmit && pnpm vitest run 2>&1 | grep -E 'Tests ')

echo "== web: tsc =="
(cd apps/web && pnpm exec tsc -p tsconfig.json --noEmit && echo ok)

echo "== containers =="
docker compose ps --format '{{.Name}} {{.Status}}'

echo "== live health =="
curl -sf localhost:8000/healthz && echo " (api)"
curl -sf localhost:8001/health && echo " (quant)"
curl -sf localhost:3100/api/health && echo " (web)"

echo "== data quality =="
curl -sf "localhost:8001/v1/data/quality?symbol=XAUUSD" | python3 -c "import json,sys; d=json.load(sys.stdin); print('overall:', d['overall'])"

echo "ALL CHECKS DONE"
