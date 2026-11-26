"""Crypto order-flow (OpenMarket Data API): per-side trade candles for
BTC/ETH/SOL plus derivatives state (OI, funding, liquidations). Free tier
budget: 10 weight/min, 1000/day — the cadences below total ~650/day."""

from __future__ import annotations

from typing import Union

from alembic import op

revision: str = "0023_crypto_flow"
down_revision: Union[str, None] = "0022_prediction_audit"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS crypto_candles (
            symbol VARCHAR(8) NOT NULL,
            market_ts TIMESTAMPTZ NOT NULL,
            open NUMERIC(18,6) NOT NULL,
            high NUMERIC(18,6) NOT NULL,
            low NUMERIC(18,6) NOT NULL,
            close NUMERIC(18,6) NOT NULL,
            buy_volume NUMERIC(20,2),
            sell_volume NUMERIC(20,2),
            exchanges INT,
            PRIMARY KEY (symbol, market_ts)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS crypto_deriv (
            symbol VARCHAR(8) NOT NULL,
            market_ts TIMESTAMPTZ NOT NULL,
            open_interest NUMERIC(20,2),
            funding_rate NUMERIC(12,8),
            liq_buy NUMERIC(20,2),
            liq_sell NUMERIC(20,2),
            PRIMARY KEY (symbol, market_ts)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_cc_ts ON crypto_candles (market_ts DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_cd_ts ON crypto_deriv (market_ts DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS crypto_deriv")
    op.execute("DROP TABLE IF EXISTS crypto_candles")
