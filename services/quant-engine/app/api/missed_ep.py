"""Missed-opportunity endpoints (§10) + signal history page data."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.db import get_pool
from signals.backtest import run_signal_backtest
from signals.missed import scan_missed

router = APIRouter(prefix="/v1/signals", tags=["missed-opportunities"])


@router.post("/missed-scan")
def missed_scan(
    symbol: str = Query(default="XAUUSD"),
    interval: str = Query(default="1h"),
    lookback_days: int = Query(default=30, ge=7, le=120),
) -> dict:
    return scan_missed(symbol.upper(), interval, lookback_days)


@router.get("/missed")
def missed(
    symbol: str = Query(default="XAUUSD"),
    interval: str = Query(default="1h"),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    with get_pool().connection() as conn:
        cur = conn.execute(
            """
            SELECT m.id, m.move_time, m.move_pct, m.direction, m.detected_by, m.blocked_by,
                   s.signal_type AS prior_type, s.created_at AS prior_created
            FROM missed_opportunities m
            LEFT JOIN trading_signals s ON s.id = m.signal_id
            WHERE m.symbol = %s AND m.interval = %s
            ORDER BY m.move_time DESC LIMIT %s
            """,
            (symbol.upper(), interval, limit),
        )
        rows = cur.fetchall()
    return {
        "count": len(rows),
        "missed": [
            {
                "move_time": r["move_time"].isoformat() if r["move_time"] else None,
                "move_pct": float(r["move_pct"]),
                "direction": r["direction"],
                "detected_by": r["detected_by"],
                "blocked_by": r["blocked_by"],
                "prior_signal": r["prior_type"],
            }
            for r in rows
        ],
    }


@router.post("/backtest")
def signal_backtest(
    symbol: str = Query(default="XAUUSD"),
    interval: str = Query(default="1h"),
    days: int = Query(default=30, ge=7, le=120),
    step_hours: int = Query(default=4, ge=1, le=24),
) -> dict:
    """Replay deterministic signal rules on prefixes; pessimistic grading.

    TECHNICAL-ONLY scope: historical news sentiment cannot be reconstructed,
    so the news vote and veto are absent for most of the window. Threshold
    sanity check, not a performance promise.
    """
    return run_signal_backtest(symbol.upper(), interval, days, step_hours)
