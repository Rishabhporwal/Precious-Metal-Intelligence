"""Data-quality monitor: staleness + missing-candle detection.

Deterministic checks over stored data; results feed the status page and the
AI analyst's data-quality warnings. No fabrication — gaps are reported, not
filled.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.db import get_pool
from app.marketdata import store
from providers.base import CandleInterval

# expected bar spacing per interval (in minutes); gold trades ~23h/day on weekdays
EXPECTED_SPACING_MIN = {
    "1min": 1,
    "5min": 5,
    "15min": 15,
    "30min": 30,
    "1h": 60,
    "4h": 240,
    "1day": 1440,
}


def quality_report(symbol: str = "XAUUSD") -> dict:
    symbol = symbol.upper()
    now = datetime.now(UTC)
    checks: list[dict] = []

    with get_pool().connection() as conn:
        inst = store.get_instrument_by_symbol(conn, symbol)
        if inst is None:
            return {"error": f"unknown instrument {symbol}"}
        q = store.get_latest_quote(conn, inst["id"])

        for interval in (CandleInterval.MIN_15, CandleInterval.HOUR_1, CandleInterval.DAY_1):
            rows = store.get_candles(conn, inst["id"], interval, limit=200)
            if not rows:
                # 15m is not ingested (credit budget) — informational, not degradation.
                ingested = interval in (CandleInterval.HOUR_1, CandleInterval.DAY_1)
                checks.append({
                    "interval": interval.value,
                    "status": "empty" if ingested else "not_ingested",
                    "detail": "no candles stored" if ingested else "interval not ingested (credit budget)",
                })
                continue
            last_ts = rows[-1]["market_ts"]
            age_hours = (now - last_ts).total_seconds() / 3600
            stale = age_hours > _staleness_threshold(interval)
            # missing-bar scan over the most recent 100 bars
            gaps = 0
            spacing = EXPECTED_SPACING_MIN.get(interval.value, 60)
            for a, b in zip(rows[-101:-1], rows[-100:], strict=False):
                dt_min = (b["market_ts"] - a["market_ts"]).total_seconds() / 60
                # weekend/holiday tolerance: gap > 2.5× spacing counts, > 3 days ignored
                if spacing * 2.5 < dt_min < 60 * 24 * 3:
                    gaps += 1
            checks.append({
                "interval": interval.value,
                "status": "stale" if stale else "ok",
                "last_candle": last_ts.isoformat(),
                "age_hours": round(age_hours, 1),
                "gaps_last_100": gaps,
                "candles": len(rows),
            })

    quote_age_min = None
    if q and q["received_at"]:
        quote_age_min = round((now - q["received_at"]).total_seconds() / 60, 1)

    overall = "ok"
    if any(c.get("status") in ("stale", "empty") for c in checks):
        overall = "degraded"
    if quote_age_min is None or quote_age_min > 20:
        overall = "degraded"

    return {
        "symbol": symbol,
        "checked_at": now.isoformat(),
        "overall": overall,
        "quote_age_min": quote_age_min,
        "checks": checks,
    }


def _staleness_threshold(interval: CandleInterval) -> float:
    """Hours after which an interval's newest candle is considered stale."""
    return {
        CandleInterval.MIN_15: 2.0,
        CandleInterval.HOUR_1: 8.0,
        CandleInterval.DAY_1: 72.0,  # weekends
    }.get(interval, 24.0)
