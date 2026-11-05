"""Event reactions — measured gold response vs hypothesis (enhancement §5.1)."""

from __future__ import annotations

from typing import Union

from alembic import op

revision: str = "0013_event_reactions"
down_revision: Union[str, None] = "0012_news_events"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS event_reactions (
            event_id BIGINT PRIMARY KEY REFERENCES news_events(id) ON DELETE CASCADE,
            measured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            pre_return_pct NUMERIC(10,3),
            post_return_pct NUMERIC(10,3),
            verdict VARCHAR(16) NOT NULL,
            detail JSONB NOT NULL DEFAULT '{}',
            CONSTRAINT ck_reaction_verdict CHECK (verdict IN
                ('confirms','contradicts','ambiguous','pending','insufficient_data'))
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS event_reactions")
