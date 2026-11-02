"""Market data store integration tests — require a live Postgres (docker).
Skipped automatically when DATABASE_URL(_HOST) is unavailable."""

import os
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from providers.base import CandleInterval, NormalizedCandle, VolumeType

pytestmark = pytest.mark.skipif(
    not (os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_HOST")),
    reason="no database URL configured",
)


def _connect():
    import psycopg
    from psycopg.rows import dict_row

    # Host-run tests must reach the host-mapped port, so HOST wins.
    url = os.environ.get("DATABASE_URL_HOST") or os.environ.get("DATABASE_URL")
    return psycopg.connect(url, row_factory=dict_row)


@pytest.fixture
def conn():
    with _connect() as c:
        yield c


@pytest.fixture
def gold_instrument(conn):
    cur = conn.execute("SELECT id FROM instruments WHERE symbol = 'XAUUSD'")
    row = cur.fetchone()
    if row is None:
        pytest.skip("instruments not seeded")
    cur = conn.execute("SELECT id FROM data_providers WHERE name = 'twelvedata'")
    provider = cur.fetchone()
    return int(row["id"]), int(provider["id"])


def _candle(ts: datetime, close: str) -> NormalizedCandle:
    c = Decimal(close)
    return NormalizedCandle(
        market_ts=ts,
        open=Decimal("100.0"),
        high=c + Decimal("1.0"),  # always >= close -> satisfies ck_candles_ohlc_sane
        low=Decimal("99.0"),
        close=c,
        volume=None,
        volume_type=VolumeType.NONE,
    )


def test_candle_dedup_and_correction(conn, gold_instrument):
    from app.marketdata import store

    instrument_id, provider_id = gold_instrument
    interval = CandleInterval.MIN_5
    ts = datetime(2026, 1, 2, 10, 0, tzinfo=UTC)

    store.upsert_candles(conn, instrument_id, provider_id, interval, [_candle(ts, "100.5")])
    store.upsert_candles(conn, instrument_id, provider_id, interval, [_candle(ts, "100.9")])

    cur = conn.execute(
        "SELECT COUNT(*) AS n FROM market_candles WHERE instrument_id = %s AND interval = %s AND market_ts = %s",
        (instrument_id, interval.value, ts),
    )
    assert cur.fetchone()["n"] == 1  # deduplicated, not duplicated

    cur = conn.execute(
        "SELECT close FROM market_candles WHERE instrument_id = %s AND interval = %s AND market_ts = %s",
        (instrument_id, interval.value, ts),
    )
    assert cur.fetchone()["close"] == Decimal("100.9")  # corrected to latest observation

    # cleanup
    conn.execute(
        "DELETE FROM market_candles WHERE instrument_id = %s AND interval = %s AND market_ts = %s",
        (instrument_id, interval.value, ts),
    )


def test_candle_asc_ordering_and_limit(conn, gold_instrument):
    from app.marketdata import store

    instrument_id, provider_id = gold_instrument
    interval = CandleInterval.MIN_5
    base = datetime(2026, 1, 3, tzinfo=UTC)
    candles = [_candle(base.replace(minute=5 * i), str(100 + i)) for i in range(5)]
    store.upsert_candles(conn, instrument_id, provider_id, interval, candles)
    try:
        rows = store.get_candles(conn, instrument_id, interval, limit=3)
        assert len(rows) == 3
        assert rows[0]["market_ts"] < rows[1]["market_ts"] < rows[2]["market_ts"]
    finally:
        conn.execute(
            "DELETE FROM market_candles WHERE instrument_id = %s AND interval = %s AND market_ts >= %s",
            (instrument_id, interval.value, base),
        )


def test_bad_ohlc_rejected_by_constraint(conn, gold_instrument):
    import psycopg

    from app.marketdata import store

    instrument_id, provider_id = gold_instrument
    bad = NormalizedCandle(
        market_ts=datetime(2026, 1, 4, tzinfo=UTC),
        open=Decimal(100),
        high=Decimal(90),  # high < open -> violates ck_candles_ohlc_sane
        low=Decimal(95),
        close=Decimal(98),
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        store.upsert_candles(conn, instrument_id, provider_id, CandleInterval.MIN_5, [bad])
