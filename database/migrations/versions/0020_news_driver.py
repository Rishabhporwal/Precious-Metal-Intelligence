"""News driver taxonomy — each classified headline gets its gold-driver category
(rates / usd / geopolitics / physical / positioning / market / other), so the
verdict engine can weigh "war escalation" differently from "rate hike".
"""

from __future__ import annotations

from typing import Union

from alembic import op

revision: str = "0020_news_driver"
down_revision: Union[str, None] = "0019_drop_alert_tables"


def upgrade() -> None:
    op.execute("ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS driver VARCHAR(16)")


def downgrade() -> None:
    op.execute("ALTER TABLE news_articles DROP COLUMN IF EXISTS driver")
