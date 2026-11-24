"""Prediction audit — every verdict plan tracked level-by-level with
achieved/not-achieved status and the deterministic reason why."""

from __future__ import annotations

from typing import Union

from alembic import op

revision: str = "0022_prediction_audit"
down_revision: Union[str, None] = "0021_gld_holdings"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS prediction_audit (
            id BIGSERIAL PRIMARY KEY,
            verdict_id BIGINT REFERENCES daily_verdicts(id),
            symbol VARCHAR(16) NOT NULL,
            direction VARCHAR(12) NOT NULL,
            mode VARCHAR(16) NOT NULL DEFAULT 'pullback',
            entry_low NUMERIC(12,2), entry_high NUMERIC(12,2),
            stop NUMERIC(12,2), t1 NUMERIC(12,2), t2 NUMERIC(12,2),
            horizon_days INT NOT NULL DEFAULT 5,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            status VARCHAR(24) NOT NULL DEFAULT 'pending',
            entry_filled_at TIMESTAMPTZ,
            t1_hit_at TIMESTAMPTZ, t2_hit_at TIMESTAMPTZ,
            stopped_at TIMESTAMPTZ,
            max_favorable NUMERIC(12,2),
            graded_at TIMESTAMPTZ,
            reason TEXT,
            CONSTRAINT ck_pa_status CHECK (status IN
                ('pending','hit_t1','hit_t2','stopped','stopped_pre_entry','superseded','expired'))
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_pa_symbol ON prediction_audit (symbol, created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS prediction_audit")
