# Implementation Status

Last updated: Phase 1 completion.

## Phases

| Phase | Scope                               | Status                 |
| ----- | ----------------------------------- | ---------------------- |
| 0     | Platform bootstrap                  | ✅ complete (verified) |
| 1     | Market data (Twelve Data, backfill) | ✅ complete (verified) |
| 2     | Dashboard                           | ⬜ not started         |
| 3     | Technical analysis                  | ⬜ not started         |
| 4     | Advanced strategies (SMC/ICT/…)     | ⬜ not started         |
| 5     | Macro & news                        | ⬜ not started         |
| 6     | Quantitative engine                 | ⬜ not started         |
| 7     | AI analyst (LangGraph)              | ⬜ not started         |
| 8     | Trading intelligence, alerts, paper | ⬜ not started         |
| 9     | Backtesting                         | ⬜ not started         |
| 10    | Hardening                           | ⬜ not started         |

## Phase 1 — completed features

- Migration `0002_market_data`: `instruments`, `data_providers`,
  `provider_observations`, `market_quotes`, `market_candles` — `market_candles`
  is a TimescaleDB hypertable whose composite PK doubles as the dedup
  constraint; OHLC-sanity / volume-type / candle-status CHECK constraints.
- Seed script: 8 instruments (XAUUSD, XAGUSD, EURUSD, USDJPY, DXY, WTI, BRENT,
  COPPER) + 5 providers. All instruments start `enabled=false` — nothing is
  ingested until entitlement is **verified against the live API**.
- Twelve Data adapter (`providers/twelve_data.py`): normalized candles/quotes
  (Decimal, UTC), token-bucket rate limiter, exponential-backoff retries on
  429/5xx/network only, honest error mapping (auth/entitlement/rate-limit),
  volume labeled `tick` (never presented as exchange volume), newest candle
  `provisional`, deterministic ascending order.
- Ingestion worker (`python -m ingestion`, own compose service): startup backfill
  (1day + 1h) + quote polling + 1min-candle refresh. Free-plan credit economy:
  ~768 credits/day at defaults (quotes every 5 min, 1min refresh every 15 min,
  2 instruments).
- Quant API `/v1`: instruments list, per-instrument verify / backfill / candles /
  quote, data status.
- Fastify gateway `/api/v1/markets*`: validation + error envelopes, pure proxy.
- Web `/markets` page: live gold/silver price cards with 90-day sparklines,
  per-instrument ingestion table with freshness + verification notes.

## Phase 1 — verified results (live)

| Instrument | Provider symbol | Daily candles | Hourly candles | Note |
|---|---|---|---|---|
| XAUUSD | XAU/USD | 5,000 (from 2007-08-29) | 5,000 | verified, enabled |
| XAGUSD | **SI** (COMEX futures) | 316 | 2,199 | spot XAG/USD needs a Grow/Venture plan — SI used as an honest futures proxy, noted in the registry |

- Live quote ingested at verification time: gold 3,907.26 @ 2026-11-01T20:00Z.
- 6 other instruments stay disabled pending entitlement verification (deliberate).
- Free-plan limitation documented: XAG/USD spot is paywalled by the provider —
  the system reports it honestly instead of substituting mock data.

## Tests executed (Phase 1)

- quant: pytest 14/14 — adapter normalization (ascending order, tick-volume
  labeling, provisional marking), error mapping (401/429/404), retry-on-5xx,
  verify flow; store integration against live TimescaleDB (dedup, correction
  upsert, ordering, OHLC-constraint rejection)
- api: vitest 2/2, tsc clean; ruff clean; Next.js production build clean

## Fixes made during Phase 1 verification

1. TimescaleDB hypertable requires the partition column in every unique index —
   `market_candles` moved from surrogate-id PK to composite PK (also the dedup).
2. psycopg3 rows must be fetched from the cursor returned by `Connection.execute`,
   not the connection (fixed across store/worker/tests).
3. `DATABASE_URL_HOST` precedence centralized in `app/db.py` (host tooling wins;
   containers only set `DATABASE_URL`).
4. Connection pool missing `row_factory=dict_row` (tuples masquerading as dicts).
5. Provider factory extracted from the ingestion worker (API no longer imports
   worker side effects).

## Known issues / limitations

- Web port is **3100** (deliberate deviation: 3000 is used by the operator's other project).
- `scheduler` compose service remains reserved for Phase 5.
- SI history depth limited (~1 year on the free plan).
- Twelve Data credits: polling defaults keep ~92% daily headroom under the 800 cap.

## Next implementation tasks (Phase 2)

1. TradingView Lightweight Charts (real candles from the API)
2. Dashboard page (market ticker, key levels from stored data, freshness)
3. WebSocket updates from api
4. Data-quality panel (stale-data warnings, missing-candle detection)
