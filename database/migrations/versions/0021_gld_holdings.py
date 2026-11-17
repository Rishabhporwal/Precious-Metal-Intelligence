"""GLD ETF daily holdings — the physical-demand driver (SPDR official archive)."""

from __future__ import annotations

from typing import Union

from alembic import op

revision: str = "0021_gld_holdings"
down_revision: Union[str, None] = "0020_news_driver"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS gld_holdings (
            date DATE PRIMARY KEY,
            tonnes NUMERIC(12,3) NOT NULL,
            closing_price NUMERIC(12,4)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS gld_holdings")
