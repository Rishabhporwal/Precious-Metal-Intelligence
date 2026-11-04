"""Trading signals — persisted at decision time, graded against outcomes."""

from __future__ import annotations

from typing import Union

from alembic import op

revision: str = "0011_trading_signals"
down_revision: Union[str, None] = "0010_strategy_evaluations"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS trading_signals (
            id BIGSERIAL PRIMARY KEY,
            symbol VARCHAR(16) NOT NULL,
            interval VARCHAR(8) NOT NULL,
            signal_type VARCHAR(16) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at TIMESTAMPTZ,
            price NUMERIC(20,8),
            score NUMERIC(8,2),
            regime VARCHAR(64),
            confidence VARCHAR(8),
            drivers JSONB NOT NULL DEFAULT '[]',
            plan JSONB,
            invalidation_level NUMERIC(20,8),
            regime_snapshot JSONB NOT NULL DEFAULT '{}',
            strategy_relevance JSONB NOT NULL DEFAULT '[]',
            note TEXT,
            graded BOOLEAN NOT NULL DEFAULT false,
            CONSTRAINT ck_signal_type CHECK (signal_type IN
                ('BUY','STRONG_BUY','SELL','STRONG_SELL','EARLY_BUY','EARLY_SELL','WAIT','NO_TRADE','INVALIDATED'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS signal_outcomes (
            signal_id BIGINT PRIMARY KEY REFERENCES trading_signals(id) ON DELETE CASCADE,
            graded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            exit_reason VARCHAR(48),
            r_multiple NUMERIC(10,3),
            mfe NUMERIC(10,3),
            mae NUMERIC(10,3),
            direction_move_pct NUMERIC(10,3),
            detail JSONB NOT NULL DEFAULT '{}'
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_signals_symbol_ts ON trading_signals (symbol, interval, created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS signal_outcomes")
    op.execute("DROP TABLE IF EXISTS trading_signals")
