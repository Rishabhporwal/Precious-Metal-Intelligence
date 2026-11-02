"""phase 5: macro & news tables

macro_observations (append-only series observations with fetch vintage),
economic_events (release calendar w/ actuals), news_articles (raw + classified
fields filled only when a classifier runs).

Revision ID: 0005_macro_news
Revises: 0004_strategies
Create Date: 2026-11-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_macro_news"
down_revision: Union[str, None] = "0004_strategies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "macro_observations",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),  # fred | cftc
        sa.Column("series_id", sa.String(64), nullable=False),  # FRED series or CFTC market key
        sa.Column("title", sa.String(256)),
        sa.Column("units", sa.String(64)),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("value", sa.Numeric(30, 8)),  # nullable for non-numeric observations
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("fetched_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("provider", "series_id", "as_of_date", "fetched_at",
                            name="uq_macro_vintage"),
    )
    op.create_index("ix_macro_series_date", "macro_observations", ["provider", "series_id", "as_of_date"])

    op.create_table(
        "economic_events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source", sa.String(32), nullable=False),  # fred_release
        sa.Column("release_name", sa.String(128), nullable=False),
        sa.Column("series_id", sa.String(64)),
        sa.Column("event_date", sa.Date(), nullable=False),  # scheduled/actual release date
        sa.Column("actual_value", sa.Numeric(30, 8)),
        sa.Column("units", sa.String(64)),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("source", "release_name", "series_id", "event_date",
                            name="uq_economic_event"),
    )
    op.create_index("ix_events_date", "economic_events", ["event_date"])

    op.create_table(
        "news_articles",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("url", sa.String(1024), nullable=False, unique=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("summary", sa.Text()),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("fetched_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("classified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sentiment", sa.String(16)),  # bullish | bearish | neutral — set only by classifier
        sa.Column("instruments", sa.JSON(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.CheckConstraint("sentiment IN ('bullish','bearish','neutral') OR sentiment IS NULL",
                           name="ck_news_sentiment"),
    )
    op.create_index("ix_news_published", "news_articles", ["published_at"])


def downgrade() -> None:
    op.drop_table("news_articles")
    op.drop_table("economic_events")
    op.drop_table("macro_observations")
