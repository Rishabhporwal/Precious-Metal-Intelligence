"""Event-reaction measurement + cross-market summary endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query

from app.db import get_pool
from app.marketdata import store
from news.reactions import measure_reaction
from providers.base import CandleInterval
from quant.cross_market import cross_market_summary

router = APIRouter(prefix="/v1/intelligence", tags=["intelligence"])


@router.post("/measure-reactions")
def measure_all(symbol: str = Query(default="XAUUSD")) -> dict:
    """Measure gold's actual reaction for every open event; upsert results."""
    symbol = symbol.upper()
    now = datetime.now(UTC)
    with get_pool().connection() as conn:
        inst = store.get_instrument_by_symbol(conn, symbol)
        if inst is None:
            raise HTTPException(status_code=404, detail=f"unknown instrument {symbol}")
        candles = store.get_candles(conn, inst["id"], CandleInterval.HOUR_1, limit=300)
        events = conn.execute(
            """
            SELECT e.id, e.title, e.gold_impact, e.last_update,
                   COALESCE(MIN(a.published_at), e.first_seen) AS event_time
            FROM news_events e
            LEFT JOIN news_articles a ON a.event_id = e.id
            WHERE e.status = 'open'
            GROUP BY e.id ORDER BY e.last_update DESC LIMIT 30
            """
        ).fetchall()
    counted = {"confirms": 0, "contradicts": 0, "ambiguous": 0, "pending": 0, "insufficient": 0}
    with get_pool().connection() as conn:
        for e in events:
            event_time = e["event_time"]
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=__import__("datetime").UTC)
            r = measure_reaction(e["gold_impact"], event_time, candles, now=now)
            if r is None:
                counted["insufficient"] += 1
                continue
            counted[r["verdict"] if r["verdict"] in counted else "insufficient"] += 1
            conn.execute(
                """
                INSERT INTO event_reactions (event_id, measured_at, pre_return_pct, post_return_pct, verdict, detail)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (event_id) DO UPDATE SET
                    measured_at = EXCLUDED.measured_at,
                    pre_return_pct = EXCLUDED.pre_return_pct,
                    post_return_pct = EXCLUDED.post_return_pct,
                    verdict = EXCLUDED.verdict,
                    detail = EXCLUDED.detail
                """,
                (e["id"], now, r.get("pre_return_pct"), r.get("post_return_pct"),
                 r["verdict"], __import__("json").dumps(r)),
            )
    return {"symbol": symbol, "measured": len(events), **counted}


@router.get("/cross-market")
def cross_market(symbol: str = Query(default="XAUUSD"), days: int = Query(default=60, ge=30, le=180)) -> dict:
    result = cross_market_summary(symbol, days)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result
