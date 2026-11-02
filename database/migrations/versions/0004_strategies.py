"""phase 4: strategy intelligence tables

strategy_detections (append-only detection records) + strategy_configs
(per-strategy enable/params, overrides seed defaults) + market_structure_events
(persisted BOS/CHoCH events from the structure engine).

Revision ID: 0004_strategies
Revises: 0002_market_data
Create Date: 2026-11-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_strategies"
down_revision: Union[str, None] = "0002_market_data"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "strategy_configs",
        sa.Column("strategy_id", sa.String(64), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("params", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "strategy_detections",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("strategy_id", sa.String(64), nullable=False),
        sa.Column("algo_version", sa.String(32), nullable=False),
        sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("interval", sa.String(8), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),  # bullish | bearish | neutral
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),  # active | consumed | expired
        sa.Column("anchor_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("detected_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("levels", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("params", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint(
            "strategy_id", "instrument_id", "interval", "anchor_time",
            name="uq_detection_identity",
        ),
        sa.CheckConstraint("direction IN ('bullish','bearish','neutral')", name="ck_det_direction"),
        sa.CheckConstraint("status IN ('active','consumed','expired')", name="ck_det_status"),
    )
    op.create_index("ix_det_symbol_interval_time", "strategy_detections",
                    ["instrument_id", "interval", "anchor_time"])

    op.create_table(
        "market_structure_events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("interval", sa.String(8), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),  # bos_bullish | bos_bearish | choch_bullish | choch_bearish
        sa.Column("event_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("level", sa.Numeric(20, 8), nullable=False),
        sa.Column("algo_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("instrument_id", "interval", "kind", "event_time",
                            name="uq_structure_event"),
        sa.CheckConstraint(
            "kind IN ('bos_bullish','bos_bearish','choch_bullish','choch_bearish')",
            name="ck_mse_kind",
        ),
    )


def downgrade() -> None:
    op.drop_table("market_structure_events")
    op.drop_table("strategy_detections")
    op.drop_table("strategy_configs")
