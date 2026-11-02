# Database Schema

Engine: PostgreSQL 16 + TimescaleDB. All timestamps UTC. Financial values in
NUMERIC/DECIMAL. Schema evolves exclusively through Alembic migrations in
`database/migrations/versions/`.

## Phase 0 (applied)

| Table               | Purpose                                                    |
| ------------------- | ---------------------------------------------------------- |
| `platform_metadata` | Schema/phase bookkeeping (`key`, `value`, timestamps).      |
| extension           | `timescaledb` (idempotent `CREATE EXTENSION`).              |

## Phase 1+ (planned, not yet implemented)

`instruments`, `data_providers`, `provider_observations`, `market_quotes`,
`market_candles`, `economic_events`, `macro_observations`, `news_articles`,
`news_impacts`, `technical_indicators`, `market_structure_events`,
`strategy_detections`, `market_analyses`, `analysis_evidence`, `trade_setups`,
`trade_outcomes`, `alert_rules`, `alert_events`, `backtest_runs`,
`backtest_trades`, `paper_accounts`, `paper_trades`, `paper_trade_fills`.

Design rules (enforced at migration time, per master spec):
- provider observations preserved raw; canonical candles derived
- duplicate candles prevented by unique constraints
- algorithm/model/prompt versions tracked
- historical analysis append-only
