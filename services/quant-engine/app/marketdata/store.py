"""Market data persistence: canonical candles + quotes + raw provider observations.

Rules implemented here:
- canonical candles are deduplicated on (instrument_id, interval, market_ts);
  re-received data corrects the candle (provider corrections are legitimate)
- provider raw responses land in provider_observations untouched
- timestamps are UTC end-to-end
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

from psycopg import Connection
from psycopg.rows import dict_row

from providers.base import CandleInterval, NormalizedCandle, NormalizedQuote, VolumeType


def _utc(dt: datetime) -> datetime:
    return dt.astimezone(UTC) if dt.tzinfo else dt.replace(tzinfo=UTC)


def record_observation(
    conn: Connection,
    provider_id: int,
    provider_symbol: str,
    endpoint: str,
    raw_payload: dict,
    ok: bool,
    error_message: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO provider_observations
            (provider_id, provider_symbol, endpoint, raw_payload, ok, error_message)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (provider_id, provider_symbol, endpoint, json.dumps(raw_payload, default=str), ok, error_message),
    )


def upsert_quote(
    conn: Connection, instrument_id: int, provider_id: int, quote: NormalizedQuote
) -> None:
    conn.execute(
        """
        INSERT INTO market_quotes
            (instrument_id, provider_id, price, bid, ask, market_ts)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (instrument_id, provider_id, quote.price, quote.bid, quote.ask, _utc(quote.market_ts)),
    )


def upsert_candles(
    conn: Connection,
    instrument_id: int,
    provider_id: int,
    interval: CandleInterval,
    candles: list[NormalizedCandle],
) -> int:
    """Insert-or-correct canonical candles. Returns number of rows written."""
    if not candles:
        return 0
    written = 0
    for c in candles:
        conn.execute(
            """
            INSERT INTO market_candles
                (instrument_id, interval, provider_id, open, high, low, close,
                 volume, volume_type, market_ts, candle_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (instrument_id, interval, market_ts) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                volume_type = EXCLUDED.volume_type,
                candle_status = EXCLUDED.candle_status,
                received_at = now()
            """,
            (
                instrument_id, interval.value, provider_id,
                c.open, c.high, c.low, c.close,
                c.volume, c.volume_type.value, _utc(c.market_ts), c.status,
            ),
        )
        written += 1
    return written


def get_instrument_by_symbol(conn: Connection, symbol: str) -> dict | None:
    cur = conn.execute("SELECT * FROM instruments WHERE symbol = %s", (symbol,))
    return cur.fetchone()


def list_instruments(conn: Connection) -> list[dict]:
    cur = conn.execute(
        """
        SELECT i.id, i.symbol, i.name, i.asset_class, i.enabled, i.entitlement_verified,
               i.verification_note, i.provider_symbol, p.name AS provider_name
        FROM instruments i
        LEFT JOIN data_providers p ON p.id = i.provider_id
        ORDER BY i.id
        """
    )
    return cur.fetchall()


def set_entitlement(
    conn: Connection,
    instrument_id: int,
    provider_symbol: str,
    verified: bool,
    enabled: bool,
    note: str,
) -> None:
    conn.execute(
        """
        UPDATE instruments
        SET provider_symbol = %s,
            entitlement_verified = %s,
            enabled = %s,
            verification_note = %s,
            updated_at = now()
        WHERE id = %s
        """,
        (provider_symbol, verified, enabled, note, instrument_id),
    )


def get_candles(
    conn: Connection,
    instrument_id: int,
    interval: CandleInterval,
    limit: int = 500,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[dict]:
    clauses = ["instrument_id = %s", "interval = %s"]
    params: list = [instrument_id, interval.value]
    if start is not None:
        clauses.append("market_ts >= %s")
        params.append(_utc(start))
    if end is not None:
        clauses.append("market_ts <= %s")
        params.append(_utc(end))
    params.append(limit)
    cur = conn.execute(
        f"""
        SELECT market_ts, open, high, low, close, volume, volume_type, candle_status
        FROM market_candles
        WHERE {" AND ".join(clauses)}
        ORDER BY market_ts DESC
        LIMIT %s
        """,
        params,
    )
    rows = cur.fetchall()
    rows.reverse()  # ascending by time
    return rows


def get_latest_quote(conn: Connection, instrument_id: int) -> dict | None:
    cur = conn.execute(
        """
        SELECT price, bid, ask, market_ts, received_at
        FROM market_quotes
        WHERE instrument_id = %s
        ORDER BY market_ts DESC
        LIMIT 1
        """,
        (instrument_id,),
    )
    return cur.fetchone()


def candle_counts(conn: Connection) -> dict[str, dict]:
    cur = conn.execute(
        """
        SELECT i.symbol,
               COALESCE(MAX(c.market_ts) FILTER (WHERE c.interval = '1day'), NULL) AS last_daily,
               COALESCE(MAX(c.market_ts) FILTER (WHERE c.interval = '1h'), NULL) AS last_hourly,
               COUNT(*) FILTER (WHERE c.interval = '1day') AS daily_count,
               COUNT(*) FILTER (WHERE c.interval = '1h') AS hourly_count
        FROM instruments i
        LEFT JOIN market_candles c ON c.instrument_id = i.id
        GROUP BY i.symbol
        """
    )
    return {r["symbol"]: r for r in cur.fetchall()}


def rows_to_dicts(rows) -> list[dict]:
    """Convert Decimals/dates for JSON responses without precision loss."""
    out = []
    for r in rows:
        d = dict(r)
        for k, v in d.items():
            if isinstance(v, Decimal):
                d[k] = str(v)
            elif isinstance(v, datetime):
                d[k] = v.isoformat()
        out.append(d)
    return out


def get_connection_kwargs() -> dict:
    return {"row_factory": dict_row}


__all__ = [
    "VolumeType",
    "candle_counts",
    "get_candles",
    "get_connection_kwargs",
    "get_instrument_by_symbol",
    "get_latest_quote",
    "list_instruments",
    "record_observation",
    "rows_to_dicts",
    "set_entitlement",
    "upsert_candles",
    "upsert_quote",
]
