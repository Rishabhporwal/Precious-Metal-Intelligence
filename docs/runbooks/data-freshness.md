# Runbook: Data Freshness / Stale Prices

## Symptom
- Dashboard shows old quote ("mkt HH:MMZ" far in the past) or data-quality
  endpoint reports `overall: degraded`.
- `/api/v1/data/quality` → `checks[].status == "stale"` or quote age > 20 min.

## Diagnosis
```bash
docker compose ps                    # is pmi-ingestion running?
docker logs pmi-ingestion --since 30m | tail -20
curl localhost:8001/v1/data/quality?symbol=XAUUSD
```

## Common causes
1. **Rate limit hit (Twelve Data 429)** — ingestion backs off automatically.
   Check `docker logs pmi-ingestion | grep -i '429\|rate'`. Do nothing unless
   persistent; the daily budget guard (TD_DAILY_BUDGET) exists for this.
2. **API key invalid / out of credits** — free plan = 800 req/day. Logs will
   show 401/400 with plan messages. Wait for the daily reset or upgrade.
3. **Market closed (weekend)** — gold spot closes Fri ~22:00 UTC to Sun
   ~23:00 UTC. Stale daily/hourly candles are EXPECTED; the thresholds account
   for weekends (daily = 72h). Quote staleness over the weekend is normal.
4. **Ingestion crash-looping** — `docker compose up -d --force-recreate ingestion`
   after fixing the logged error.

## Recovery
```bash
docker compose restart ingestion
sleep 30 && docker logs pmi-ingestion --since 1m | tail -5
```
Never manually insert candles — data must come from the provider.
