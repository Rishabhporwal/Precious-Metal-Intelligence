"""Strategy evaluations — preserved snapshots of the verdict engine (§16)."""

from __future__ import annotations

from typing import Union

from alembic import op

revision: str = "0010_strategy_evaluations"
down_revision: Union[str, None] = "0009_daily_verdicts"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS strategy_evaluations (
            id BIGSERIAL PRIMARY KEY,
            symbol VARCHAR(16) NOT NULL,
            interval VARCHAR(8) NOT NULL,
            price NUMERIC(20,8),
            counts JSONB NOT NULL DEFAULT '{}',
            verdicts JSONB NOT NULL DEFAULT '[]',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_evals_symbol_interval ON strategy_evaluations (symbol, interval, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS strategy_evaluations")
