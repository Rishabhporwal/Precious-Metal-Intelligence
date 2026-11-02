"""phase 1: market data core tables

instruments, data_providers, provider_observations, market_quotes,
market_candles (TimescaleDB hypertable).

Revision ID: 0002_market_data
Revises: 0001_baseline
Create Date: 2026-11-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_market_data"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CANDLE_INTERVALS = (
    "1min", "5min", "15min", "30min", "1h", "4h", "1day", "1week", "1month",
)
VOLUME_TYPES = ("none", "tick", "base", "exchange")
CANDLE_STATUSES = ("final", "provisional")


def upgrade() -> None:
    # --- data_providers (created first: instruments reference it) -------------
    op.create_table(
        "data_providers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("kind", sa.String(32), nullable=False),  # market | macro | positioning | news | calendar
        sa.Column("base_url", sa.String(256)),
        sa.Column("credentials_configured", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(16), nullable=False, server_default="unconfigured"),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # --- instruments (internal registry, provider-agnostic) -------------------
    op.create_table(
        "instruments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(32), nullable=False, unique=True),  # internal: XAUUSD
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("asset_class", sa.String(32), nullable=False),  # metal | fx | energy | index
        sa.Column("base_ccy", sa.String(8), nullable=False),
        sa.Column("quote_ccy", sa.String(8)),
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("data_providers.id")),
        sa.Column("provider_symbol", sa.String(64)),  # provider's symbol for this instrument
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("entitlement_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("verification_note", sa.Text()),
        sa.Column("contract_specs", sa.JSON()),  # instrument-specific specs (Phase 8 risk)
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # --- provider_observations (raw responses, never mutated) -----------------
    op.create_table(
        "provider_observations",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("data_providers.id"), nullable=False),
        sa.Column("provider_symbol", sa.String(64), nullable=False),
        sa.Column("endpoint", sa.String(64), nullable=False),  # quote | time_series | ...
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("received_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_provider_obs_provider_time", "provider_observations",
                    ["provider_id", "received_at"])

    # --- market_quotes (point-in-time prices) ---------------------------------
    op.create_table(
        "market_quotes",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("data_providers.id"), nullable=False),
        sa.Column("price", sa.Numeric(20, 8)),
        sa.Column("bid", sa.Numeric(20, 8)),
        sa.Column("ask", sa.Numeric(20, 8)),
        sa.Column("market_ts", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("received_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_quotes_instrument_ts", "market_quotes", ["instrument_id", "market_ts"])

    # --- market_candles (canonical OHLC, deduplicated, Timescale hypertable) --
    op.create_table(
        "market_candles",
        # Composite PK (not a surrogate id): TimescaleDB hypertables require the
        # partition column (market_ts) in every unique index, including the PK.
        # This PK also IS the dedup constraint — canonical candles never duplicate.
        sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("interval", sa.String(8), nullable=False),
        sa.Column("market_ts", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("data_providers.id"), nullable=False),
        sa.Column("open", sa.Numeric(20, 8), nullable=False),
        sa.Column("high", sa.Numeric(20, 8), nullable=False),
        sa.Column("low", sa.Numeric(20, 8), nullable=False),
        sa.Column("close", sa.Numeric(20, 8), nullable=False),
        sa.Column("volume", sa.Numeric(30, 8)),
        sa.Column("volume_type", sa.String(16), nullable=False, server_default="none"),
        sa.Column("candle_status", sa.String(16), nullable=False, server_default="final"),
        sa.Column("received_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("instrument_id", "interval", "market_ts", name="pk_candles"),
        sa.CheckConstraint("interval IN ('1min','5min','15min','30min','1h','4h','1day','1week','1month')",
                           name="ck_candles_interval"),
        sa.CheckConstraint("volume_type IN ('none','tick','base','exchange')", name="ck_candles_volume_type"),
        sa.CheckConstraint("candle_status IN ('final','provisional')", name="ck_candles_status"),
        sa.CheckConstraint("high >= low AND high >= open AND high >= close AND low <= open AND low <= close",
                           name="ck_candles_ohlc_sane"),
    )
    op.create_index("ix_candles_instrument_interval_ts", "market_candles",
                    ["instrument_id", "interval", "market_ts"])
    # Hypertable: partition key market_ts is part of the unique index, as required.
    op.execute("SELECT create_hypertable('market_candles', 'market_ts', if_not_exists => TRUE, migrate_data => TRUE)")


def downgrade() -> None:
    op.drop_table("market_candles")
    op.drop_table("market_quotes")
    op.drop_table("provider_observations")
    op.drop_table("instruments")
    op.drop_table("data_providers")
