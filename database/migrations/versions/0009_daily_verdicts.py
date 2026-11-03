"""Daily verdicts — the single synthesized call per symbol."""

from __future__ import annotations

from typing import Union

from alembic import op

revision: str = "0009_daily_verdicts"
down_revision: Union[str, None] = "0008_backtests"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_verdicts (
            id BIGSERIAL PRIMARY KEY,
            symbol VARCHAR(16) NOT NULL,
            as_of TIMESTAMPTZ NOT NULL DEFAULT now(),
            price NUMERIC(20,8),
            direction VARCHAR(12) NOT NULL,
            confidence VARCHAR(8) NOT NULL,
            score NUMERIC(8,2) NOT NULL,
            drivers JSONB NOT NULL DEFAULT '[]',
            event_risk JSONB NOT NULL DEFAULT '{}',
            plan JSONB,
            invalidations JSONB NOT NULL DEFAULT '[]',
            key_levels JSONB NOT NULL DEFAULT '{}',
            narrative TEXT,
            llm_meta JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_verdict_direction CHECK (direction IN ('bullish','bearish','neutral'))
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_verdicts_symbol_asof ON daily_verdicts (symbol, as_of DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS daily_verdicts")
