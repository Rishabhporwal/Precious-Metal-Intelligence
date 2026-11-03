"""Confluence endpoint — combines the independent strategy verdicts (§7)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.db import get_pool
from strategies.confluence_view import build_confluence

router = APIRouter(prefix="/v1/confluence", tags=["confluence"])


@router.get("/latest")
def latest(symbol: str = Query(default="XAUUSD"), interval: str = Query(default="1h")) -> dict:
    symbol = symbol.upper()
    with get_pool().connection() as conn:
        cur = conn.execute(
            """
            SELECT verdicts, created_at FROM strategy_evaluations
            WHERE symbol = %s AND interval = %s ORDER BY created_at DESC LIMIT 1
            """,
            (symbol, interval.lower()),
        )
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="no strategy evaluation yet — run POST /v1/strategy-verdicts/evaluate")
    c = build_confluence(row["verdicts"])
    return {
        "symbol": symbol,
        "interval": interval.lower(),
        "evaluated_at": row["created_at"].isoformat() if row["created_at"] else None,
        **c,
    }
