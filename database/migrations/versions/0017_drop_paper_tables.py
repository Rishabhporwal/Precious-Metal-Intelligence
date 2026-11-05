"""Drop paper-trading tables — My Practice feature removed (product prune)."""

from __future__ import annotations

from typing import Union

from alembic import op

revision: str = "0017_drop_paper_tables"
down_revision: Union[str, None] = "0016_economic_events_dedupe"


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS paper_trade_fills CASCADE")
    op.execute("DROP TABLE IF EXISTS paper_trades CASCADE")
    op.execute("DROP TABLE IF EXISTS paper_accounts CASCADE")


def downgrade() -> None:
    # no revival — feature intentionally removed
    pass
