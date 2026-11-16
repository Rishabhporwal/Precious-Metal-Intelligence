"""Drop alert tables — alerts feature removed (product prune)."""

from __future__ import annotations

from typing import Union

from alembic import op

revision: str = "0019_drop_alert_tables"
down_revision: Union[str, None] = "0018_alert_last_state"


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS alert_events CASCADE")
    op.execute("DROP TABLE IF EXISTS alert_rules CASCADE")


def downgrade() -> None:
    pass  # feature intentionally removed
