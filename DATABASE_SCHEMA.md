# Database Schema

Engine: PostgreSQL 16 + TimescaleDB. All timestamps UTC. Financial values in
NUMERIC/DECIMAL. Schema evolves exclusively through Alembic migrations in
`database/migrations/versions/`.

## Phase 0 (applied, `0001_baseline`)

| Table               | Purpose                                                    |
| ------------------- | ---------------------------------------------------------- |
| `platform_metadata` | Schema/phase bookkeeping (`key`, `value`, timestamps).      |
| extension           | `timescaledb` (idempotent `CREATE EXTENSION`).              |

## Phase 1 (applied, `0002_market_data`)

| Table                   | Key points                                                                                                       |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `instruments`           | Internal registry (`symbol` unique, e.g. XAUUSD). `provider_symbol` maps to the provider. `enabled` requires `entitlement_verified`. `contract_specs` reserved for Phase 8 risk. |
| `data_providers`        | Provider registry (`name` unique, `kind`: market/macro/positioning/news/calendar, `credentials_configured`).      |
| `provider_observations` | Raw provider responses — append-only, never mutated (`raw_payload` JSONB, `ok`, `error_message`, `received_at`).  |
| `market_quotes`         | Point-in-time prices (price/bid/ask NUMERIC(20,8), `market_ts`, `received_at`).                                   |
| `market_candles`        | **TimescaleDB hypertable** (partition key `market_ts`). Composite PK `(instrument_id, interval, market_ts)` IS the dedup constraint — re-received data corrects in place. CHECK constraints: valid interval, volume type (`none/tick/base/exchange`), candle status (`final/provisional`), OHLC sanity. `volume_type='tick'` never implies exchange volume. |

## Phase 2+ (planned, not yet implemented)

`economic_events`, `macro_observations`, `news_articles`, `news_impacts`,
`technical_indicators`, `market_structure_events`, `strategy_detections`,
`market_analyses`, `analysis_evidence`, `trade_setups`, `trade_outcomes`,
`alert_rules`, `alert_events`, `backtest_runs`, `backtest_trades`,
*(paper trading removed 2026-11-06 — tables dropped in migration 0017)*

## Standing design rules

- provider observations preserved raw; canonical candles derived
- duplicate candles prevented by the composite PK upsert
- algorithm/model/prompt versions tracked (Phase 3+)
- historical analysis append-only (Phase 7+)
- TimescaleDB rule: the partition key must appear in every unique index —
  plan PKs accordingly from the start (Phase 0 lesson).
