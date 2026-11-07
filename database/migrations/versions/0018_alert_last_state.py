"""Alert state tracking — continuously-true conditions must fire ONCE
(on false→true transition), not on every cooldown expiry. Adds last_state.
"""

from __future__ import annotations

from typing import Union

from alembic import op

revision: str = "0018_alert_last_state"
down_revision: Union[str, None] = "0017_drop_paper_tables"


def upgrade() -> None:
    op.execute("ALTER TABLE alert_rules ADD COLUMN IF NOT EXISTS last_state BOOLEAN")


def downgrade() -> None:
    op.execute("ALTER TABLE alert_rules DROP COLUMN IF EXISTS last_state")
