"""phase 9: backtesting tables

backtest_runs (params + metrics + cost model, reproducible) and
backtest_trades (per-trade records with R-multiples and costs).

Revision ID: 0008_backtests
Revises: 0007_trading
Create Date: 2026-11-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_backtests"
down_revision: Union[str, None] = "0007_trading"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("interval", sa.String(8), nullable=False),
        sa.Column("strategy_id", sa.String(64), nullable=False),
        sa.Column("algo_version", sa.String(32), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("cost_model", sa.JSON(), nullable=False),
        sa.Column("data_start", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("data_end", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("oos_metrics", sa.JSON()),
        sa.Column("leakage_excluded", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "backtest_trades",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("run_id", sa.BigInteger(), sa.ForeignKey("backtest_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("entry_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("exit_time", sa.TIMESTAMP(timezone=True)),
        sa.Column("entry_price", sa.Numeric(20, 8), nullable=False),
        sa.Column("exit_price", sa.Numeric(20, 8)),
        sa.Column("stop", sa.Numeric(20, 8)),
        sa.Column("r_multiple", sa.Numeric(10, 3)),
        sa.Column("pnl", sa.Numeric(20, 8)),
        sa.Column("costs", sa.Numeric(20, 8), server_default=sa.text("0")),
        sa.Column("exit_reason", sa.String(16)),
        sa.Column("segment", sa.String(8), nullable=False, server_default="is"),  # is | oos
    )
    op.create_index("ix_bt_trades_run", "backtest_trades", ["run_id"])


def downgrade() -> None:
    op.drop_table("backtest_trades")
    op.drop_table("backtest_runs")
