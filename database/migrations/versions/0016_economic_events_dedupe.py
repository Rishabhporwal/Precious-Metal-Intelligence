"""Economic-events dedupe fix (§16): series_id is NULL for release events and
Postgres treats NULLs as DISTINCT in unique constraints, so the old
ON CONFLICT (…, series_id, …) never matched — every calendar sync inserted
~300 duplicate rows. Replaces it with an expression index on
coalesce(series_id, '') and refreshes actual_value on conflict.
"""

from __future__ import annotations

from typing import Union

from alembic import op

revision: str = "0016_economic_events_dedupe"
down_revision: Union[str, None] = "0015_missed_opportunities"


def upgrade() -> None:
    # keep the freshest row per event (newest created_at carries the latest actual_value)
    op.execute(
        """
        DELETE FROM economic_events a
        USING economic_events b
        WHERE a.id <> b.id
          AND a.source = b.source
          AND a.release_name = b.release_name
          AND coalesce(a.series_id, '') = coalesce(b.series_id, '')
          AND a.event_date = b.event_date
          AND (b.created_at, b.id) > (a.created_at, a.id)
        """
    )
    op.execute("DROP INDEX IF EXISTS uq_economic_event_ci")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_economic_event_ci
        ON economic_events (source, release_name, coalesce(series_id, ''), event_date)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_economic_event_ci")
