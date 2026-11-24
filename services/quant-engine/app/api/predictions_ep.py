"""Prediction audit endpoints — accuracy of our calls, with reasons."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.db import get_pool
from app.predictions import audit_summary, backfill_from_history, grade_pending

router = APIRouter(prefix="/v1/predictions", tags=["prediction-audit"])


@router.post("/backfill")
def backfill(symbol: str = Query(default="XAUUSD")) -> dict:
    return {"snapshotted": backfill_from_history(symbol)}


@router.post("/grade")
def grade(symbol: str = Query(default="XAUUSD")) -> dict:
    return {"graded": grade_pending(symbol)}


@router.get("/audit")
def audit(
    symbol: str = Query(default="XAUUSD"),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    with get_pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT id, direction, mode, entry_low, entry_high, stop, t1, t2,
                   status, created_at, entry_filled_at, t1_hit_at, t2_hit_at,
                   stopped_at, max_favorable, reason
            FROM prediction_audit WHERE symbol = %s
            ORDER BY created_at DESC LIMIT %s
            """,
            (symbol.upper(), limit),
        ).fetchall()
    return {
        "count": len(rows),
        "predictions": [
            {
                "id": r["id"],
                "direction": r["direction"],
                "mode": r["mode"],
                "entry": [float(r["entry_low"]) if r["entry_low"] else None,
                          float(r["entry_high"]) if r["entry_high"] else None],
                "stop": float(r["stop"]) if r["stop"] else None,
                "t1": float(r["t1"]) if r["t1"] else None,
                "t2": float(r["t2"]) if r["t2"] else None,
                "status": r["status"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "entry_filled_at": r["entry_filled_at"].isoformat() if r["entry_filled_at"] else None,
                "t1_hit_at": r["t1_hit_at"].isoformat() if r["t1_hit_at"] else None,
                "t2_hit_at": r["t2_hit_at"].isoformat() if r["t2_hit_at"] else None,
                "stopped_at": r["stopped_at"].isoformat() if r["stopped_at"] else None,
                "max_favorable": float(r["max_favorable"]) if r["max_favorable"] else None,
                "reason": r["reason"],
            }
            for r in rows
        ],
    }


@router.get("/summary")
def summary(symbol: str = Query(default="XAUUSD")) -> dict:
    return audit_summary(symbol)
