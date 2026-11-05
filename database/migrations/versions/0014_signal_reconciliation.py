"""Signal reconciliation — the four explicit verdict groups (§9)."""

from __future__ import annotations

from typing import Union

from alembic import op

revision: str = "0014_signal_reconciliation"
down_revision: Union[str, None] = "0013_event_reactions"


def upgrade() -> None:
    op.execute("ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS reconciliation JSONB NOT NULL DEFAULT '{}'")


def downgrade() -> None:
    op.execute("ALTER TABLE trading_signals DROP COLUMN IF EXISTS reconciliation")
