"""phase 8: trading intelligence tables

trade_setups (risk-validated candidates from strategy detections, append-only),
trade_outcomes (linked to setups after paper-trading evaluation),
alert_rules + alert_events, paper_accounts + paper_trades + paper_trade_fills.

Revision ID: 0007_trading
Revises: 0006_analyst
Create Date: 2026-11-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_trading"
down_revision: Union[str, None] = "0006_analyst"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trade_setups",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("detection_id", sa.BigInteger(), sa.ForeignKey("strategy_detections.id"), nullable=False),
        sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),  # long | short
        sa.Column("entry_low", sa.Numeric(20, 8), nullable=False),
        sa.Column("entry_high", sa.Numeric(20, 8), nullable=False),
        sa.Column("stop", sa.Numeric(20, 8), nullable=False),
        sa.Column("target1", sa.Numeric(20, 8), nullable=False),
        sa.Column("target2", sa.Numeric(20, 8)),
        sa.Column("target3", sa.Numeric(20, 8)),
        sa.Column("risk_reward", sa.Numeric(10, 3), nullable=False),
        sa.Column("position_size", sa.Numeric(20, 8)),  # computed at validation (oz / units)
        sa.Column("validation_status", sa.String(16), nullable=False),  # valid | rejected
        sa.Column("validation_reasons", sa.JSON(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("risk_engine_version", sa.String(32), nullable=False),
        sa.Column("anchor_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("detection_id", "risk_engine_version", name="uq_setup_detection_version"),
        sa.CheckConstraint("direction IN ('long','short')", name="ck_setup_direction"),
        sa.CheckConstraint("validation_status IN ('valid','rejected')", name="ck_setup_validation"),
    )
    op.create_index("ix_setups_instrument_time", "trade_setups", ["instrument_id", "anchor_time"])

    op.create_table(
        "trade_outcomes",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("setup_id", sa.BigInteger(), sa.ForeignKey("trade_setups.id"), nullable=False),
        sa.Column("paper_trade_id", sa.BigInteger()),
        sa.Column("outcome", sa.String(16), nullable=False),  # win | loss | breakeven | expired
        sa.Column("r_multiple", sa.Numeric(10, 3)),
        sa.Column("evaluated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "alert_rules",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        # price_above | price_below | sweep | fvg | bos_choch | setup_new | analysis_new
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("severity", sa.String(16), nullable=False, server_default="info"),  # info | warning | critical
        sa.Column("cooldown_seconds", sa.Integer(), nullable=False, server_default=sa.text("3600")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "kind IN ('price_above','price_below','sweep','fvg','bos_choch','setup_new','analysis_new')",
            name="ck_alert_kind",
        ),
        sa.CheckConstraint("severity IN ('info','warning','critical')", name="ck_alert_severity"),
    )

    op.create_table(
        "alert_events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("rule_id", sa.BigInteger(), sa.ForeignKey("alert_rules.id"), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("delivered_telegram", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("delivery_error", sa.Text()),
        sa.Column("fired_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_alert_events_fired", "alert_events", ["fired_at"])

    op.create_table(
        "paper_accounts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("initial_balance", sa.Numeric(20, 8), nullable=False),
        sa.Column("risk_pct_per_trade", sa.Numeric(6, 3), nullable=False, server_default=sa.text("1.0")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "paper_trades",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("account_id", sa.BigInteger(), sa.ForeignKey("paper_accounts.id"), nullable=False),
        sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),  # long | short
        sa.Column("size", sa.Numeric(20, 8), nullable=False),  # oz for metals
        sa.Column("entry_price", sa.Numeric(20, 8), nullable=False),
        sa.Column("entry_time", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("stop", sa.Numeric(20, 8)),
        sa.Column("target", sa.Numeric(20, 8)),
        sa.Column("exit_price", sa.Numeric(20, 8)),
        sa.Column("exit_time", sa.TIMESTAMP(timezone=True)),
        sa.Column("exit_reason", sa.String(16)),  # stop | target | manual
        sa.Column("status", sa.String(8), nullable=False, server_default="open"),  # open | closed
        sa.Column("setup_id", sa.BigInteger(), sa.ForeignKey("trade_setups.id")),
        sa.CheckConstraint("direction IN ('long','short')", name="ck_ptrade_direction"),
        sa.CheckConstraint("status IN ('open','closed')", name="ck_ptrade_status"),
    )
    op.create_index("ix_ptrades_account_status", "paper_trades", ["account_id", "status"])

    op.create_table(
        "paper_trade_fills",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("trade_id", sa.BigInteger(), sa.ForeignKey("paper_trades.id", ondelete="CASCADE"), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),  # buy | sell
        sa.Column("qty", sa.Numeric(20, 8), nullable=False),
        sa.Column("price", sa.Numeric(20, 8), nullable=False),
        sa.Column("fee", sa.Numeric(20, 8), nullable=False, server_default=sa.text("0")),
        sa.Column("ts", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("paper_trade_fills")
    op.drop_table("paper_trades")
    op.drop_table("paper_accounts")
    op.drop_table("alert_events")
    op.drop_table("alert_rules")
    op.drop_table("trade_outcomes")
    op.drop_table("trade_setups")
