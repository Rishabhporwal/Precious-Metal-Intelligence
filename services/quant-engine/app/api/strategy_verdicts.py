"""Strategy verdicts endpoint — independent standing verdict for every strategy."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query

from app.db import get_pool
from app.marketdata import store
from providers.base import CandleInterval
from strategies import verdicts as sv
from strategies.engine import run_evaluation

router = APIRouter(prefix="/v1/strategy-verdicts", tags=["strategy-verdicts"])


@router.post("/evaluate")
def evaluate(symbol: str = Query(default="XAUUSD"), interval: str = Query(default="1h")) -> dict:
    symbol = symbol.upper()
    interval = interval.lower()
    try:
        ci = CandleInterval(interval)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"unsupported interval {interval}") from exc

    with get_pool().connection() as conn:
        inst = store.get_instrument_by_symbol(conn, symbol)
        if inst is None or not inst["enabled"]:
            raise HTTPException(status_code=409, detail=f"instrument {symbol} not available")
        candles = store.get_candles(conn, inst["id"], ci, limit=500)
        quote = store.get_latest_quote(conn, inst["id"])

    if len(candles) < sv.MIN_CANDLES:
        raise HTTPException(status_code=409, detail="insufficient candle history")

    last_close = float(candles[-1]["close"])
    price = float(quote["price"]) if quote and quote.get("price") is not None else last_close

    # run the engine fresh (persists new detections, deduped by anchor)
    run_evaluation(symbol, ci)

    with get_pool().connection() as conn:
        cur = conn.execute(
            """
            SELECT d.strategy_id, d.algo_version, d.direction, d.anchor_time,
                   d.levels, d.evidence, d.status
            FROM strategy_detections d
            JOIN instruments i ON i.id = d.instrument_id
            WHERE i.symbol = %s AND d.interval = %s
            ORDER BY d.anchor_time DESC
            """,
            (symbol, interval),
        )
        rows = cur.fetchall()

    by_strategy: dict[str, list[dict]] = {}
    for r in rows:
        by_strategy.setdefault(r["strategy_id"], []).append(r)

    out: list[dict] = []
    for sid, name in sorted(_registry_iter()):
        if sid == "composite_sweep_mss_fvg_ob":
            continue  # composite belongs to the confluence layer, not individual verdicts
        dets = by_strategy.get(sid, [])
        v = sv.classify(sid, name, dets, price, interval, len(candles))
        v["instrument"] = symbol
        v["related_strategies"] = sv.related_strategies(sid)
        out.append(v)

    counts = {"bullish": 0, "bearish": 0, "neutral": 0, "no_signal": 0, "insufficient_data": 0, "other": 0}
    for v in out:
        key = v["verdict"].lower()
        counts[key if key in counts else "other"] += 1

    result = {
        "symbol": symbol,
        "interval": interval,
        "price": price,
        "evaluated_at": datetime.now(UTC).isoformat(),
        "counts": counts,
        "verdicts": out,
    }

    # persist the snapshot (§16: preserve evaluations, never overwrite)
    with get_pool().connection() as conn:
        conn.execute(
            """
            INSERT INTO strategy_evaluations (symbol, interval, price, counts, verdicts)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (symbol, interval, price, json.dumps(counts), json.dumps(out)),
        )
    return result


def _registry_iter():
    from strategies.registry import REGISTRY

    for sid, cls in REGISTRY.items():
        yield sid, getattr(cls, "name", sid)


@router.get("/latest")
def latest(symbol: str = Query(default="XAUUSD"), interval: str = Query(default="1h")) -> dict:
    symbol = symbol.upper()
    with get_pool().connection() as conn:
        cur = conn.execute(
            """
            SELECT counts, verdicts, price, created_at FROM strategy_evaluations
            WHERE symbol = %s AND interval = %s ORDER BY created_at DESC LIMIT 1
            """,
            (symbol, interval.lower()),
        )
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="no evaluation yet — run POST /v1/strategy-verdicts/evaluate")
    return {
        "symbol": symbol,
        "interval": interval.lower(),
        "price": row["price"],
        "counts": row["counts"],
        "verdicts": row["verdicts"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }
