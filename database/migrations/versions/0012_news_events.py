"""News events — clustered global-intelligence records (enhancement spec §4)."""

from __future__ import annotations

from typing import Union

from alembic import op

revision: str = "0012_news_events"
down_revision: Union[str, None] = "0011_trading_signals"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS news_events (
            id BIGSERIAL PRIMARY KEY,
            cluster_key VARCHAR(96) NOT NULL,
            title VARCHAR(400) NOT NULL,
            category VARCHAR(24) NOT NULL DEFAULT 'other',
            region VARCHAR(64),
            entities JSONB NOT NULL DEFAULT '[]',
            importance VARCHAR(8) NOT NULL DEFAULT 'medium',
            gold_impact VARCHAR(12) NOT NULL DEFAULT 'uncertain',
            verification_status VARCHAR(12) NOT NULL DEFAULT 'UNVERIFIED',
            sources_count INTEGER NOT NULL DEFAULT 1,
            source_names JSONB NOT NULL DEFAULT '[]',
            status VARCHAR(8) NOT NULL DEFAULT 'open',
            first_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_update TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_ne_category CHECK (category IN
                ('geopolitics','central_bank','economy','elections','market','other')),
            CONSTRAINT ck_ne_importance CHECK (importance IN ('high','medium','low')),
            CONSTRAINT ck_ne_impact CHECK (gold_impact IN ('bullish','bearish','mixed','uncertain')),
            CONSTRAINT ck_ne_verification CHECK (verification_status IN
                ('CONFIRMED','REPORTED','DEVELOPING','UNVERIFIED','DENIED','CORRECTED'))
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_news_events_last ON news_events (last_update DESC)")
    op.execute("ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS event_id BIGINT REFERENCES news_events(id)")
    op.execute("ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS verification_status VARCHAR(12) DEFAULT 'UNVERIFIED'")
    op.execute("ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS importance VARCHAR(8)")
    op.execute("ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS category VARCHAR(24)")
    op.execute("ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS region VARCHAR(64)")
    op.execute("ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS entities JSONB DEFAULT '[]'")


def downgrade() -> None:
    op.execute("ALTER TABLE news_articles DROP COLUMN IF EXISTS event_id")
    op.execute("ALTER TABLE news_articles DROP COLUMN IF EXISTS verification_status")
    op.execute("ALTER TABLE news_articles DROP COLUMN IF EXISTS importance")
    op.execute("ALTER TABLE news_articles DROP COLUMN IF EXISTS category")
    op.execute("ALTER TABLE news_articles DROP COLUMN IF EXISTS region")
    op.execute("ALTER TABLE news_articles DROP COLUMN IF EXISTS entities")
    op.execute("DROP TABLE IF EXISTS news_events")
