"""Strategies API: registry, on-demand evaluation, persisted detections."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.db import get_pool
from app.marketdata import store
from providers.base import CandleInterval
from strategies import engine

router = APIRouter(prefix="/v1/strategies", tags=["strategies"])


@router.get("")
def list_strategies() -> dict:
    return {"strategies": engine.list_strategies()}


@router.get("/detections")
def detections(
    symbol: str = Query(default="XAUUSD"),
    interval: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    symbol = symbol.upper()
    with get_pool().connection() as conn:
        inst = store.get_instrument_by_symbol(conn, symbol)
    if inst is None:
        raise HTTPException(status_code=404, detail=f"unknown instrument {symbol}")
    rows = engine.recent_detections(symbol, interval, limit)
    return {
        "symbol": symbol,
        "interval": interval,
        "count": len(rows),
        "detections": [
            {
                "strategy_id": r["strategy_id"],
                "algo_version": r["algo_version"],
                "interval": r["interval"],
                "direction": r["direction"],
                "status": r["status"],
                "anchor_time": r["anchor_time"].isoformat() if r["anchor_time"] else None,
                "levels": r["levels"],
                "evidence": r["evidence"],
            }
            for r in rows
        ],
    }


class EvaluateRequest(BaseModel):
    symbol: str = "XAUUSD"
    intervals: list[CandleInterval] = [CandleInterval.MIN_15, CandleInterval.HOUR_1, CandleInterval.DAY_1]


@router.post("/evaluate")
def evaluate(req: EvaluateRequest) -> dict:
    symbol = req.symbol.upper()
    with get_pool().connection() as conn:
        inst = store.get_instrument_by_symbol(conn, symbol)
    if inst is None:
        raise HTTPException(status_code=404, detail=f"unknown instrument {symbol}")
    results = []
    for iv in req.intervals:
        try:
            results.append(engine.run_evaluation(symbol, iv))
        except Exception as exc:  # noqa: BLE001 — surface per-interval failures honestly
            results.append({"symbol": symbol, "interval": iv.value, "error": str(exc)})
    return {"symbol": symbol, "results": results}


@router.get("/{strategy_id}")
def get_strategy(strategy_id: str) -> dict:
    strategies = {s["strategy_id"]: s for s in engine.list_strategies()}
    if strategy_id not in strategies:
        raise HTTPException(status_code=404, detail=f"unknown strategy {strategy_id}")
    return strategies[strategy_id]
