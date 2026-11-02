"""phase 7: AI analyst persistence

market_analyses — append-only analysis records with model/prompt/evidence-hash
tracking (reproducibility + LLM cost-cache dedupe). analysis_evidence — the
deterministic evidence pack references backing every analysis.

Revision ID: 0006_analyst
Revises: 0005_macro_news
Create Date: 2026-11-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_analyst"
down_revision: Union[str, None] = "0005_macro_news"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "market_analyses",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("interval", sa.String(8), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),  # llm | deterministic_fallback | failed
        sa.Column("model", sa.String(128)),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("scenarios", sa.JSON(), nullable=False),
        sa.Column("risk", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("data_warnings", sa.JSON(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("summary", sa.Text()),
        sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("generated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("symbol", "interval", "evidence_hash", name="uq_analysis_evidence_hash"),
    )
    op.create_index("ix_analyses_symbol_time", "market_analyses", ["symbol", "generated_at"])

    op.create_table(
        "analysis_evidence",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("analysis_id", sa.BigInteger(), sa.ForeignKey("market_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),  # technical | strategies | macro | quant | risk | news
        sa.Column("ref", sa.String(128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_evidence_analysis", "analysis_evidence", ["analysis_id", "kind"])


def downgrade() -> None:
    op.drop_table("analysis_evidence")
    op.drop_table("market_analyses")
