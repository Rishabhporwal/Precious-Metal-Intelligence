"""Missed opportunities (§10) — coverage + blocking reasons per major move."""

from __future__ import annotations

from typing import Union

from alembic import op

revision: str = "0015_missed_opportunities"
down_revision: Union[str, None] = "0014_signal_reconciliation"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS missed_opportunities (
            id BIGSERIAL PRIMARY KEY,
            symbol VARCHAR(16) NOT NULL,
            interval VARCHAR(8) NOT NULL,
            move_time TIMESTAMPTZ NOT NULL,
            move_pct NUMERIC(10,3) NOT NULL,
            direction VARCHAR(8) NOT NULL,
            signal_id BIGINT REFERENCES trading_signals(id),
            detected_by JSONB NOT NULL DEFAULT '[]',
            blocked_by VARCHAR(32) NOT NULL,
            evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_missed_direction CHECK (direction IN ('up','down')),
            CONSTRAINT ck_missed_blocked CHECK (blocked_by IN
                ('no_signal_in_window','signal_wait','signal_no_trade','signal_opposite','covered_by_signal')),
            CONSTRAINT uq_missed_move UNIQUE (symbol, interval, move_time)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_missed_symbol ON missed_opportunities (symbol, move_time DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS missed_opportunities")
