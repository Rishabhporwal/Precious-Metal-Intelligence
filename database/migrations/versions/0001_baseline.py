"""baseline: platform metadata + TimescaleDB extension

Revision ID: 0001_baseline
Revises:
Create Date: 2026-11-02

Phase 0 baseline. Domain tables (instruments, candles, detections, ...)
land in Phase 1+ migrations on top of this baseline.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # TimescaleDB extension (idempotent). Requires the timescaledb image;
    # on plain postgres this is a no-op failure surfaced clearly at deploy time.
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    op.create_table(
        "platform_metadata",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.execute(
        "INSERT INTO platform_metadata (key, value) VALUES ('schema_baseline', 'phase-0')"
    )


def downgrade() -> None:
    op.drop_table("platform_metadata")
    # Extension is intentionally not dropped (shared object, idempotent on re-up).
