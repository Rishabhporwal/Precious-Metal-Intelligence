"""Per-strategy performance (new spec §8): evaluate + compare — real numbers only."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.api.backtests import run_backtest_for
from app.db import get_pool

router = APIRouter(prefix="/v1/performance", tags=["performance"])


@router.post("/evaluate")
def evaluate(
    symbol: str = Query(default="XAUUSD"),
    interval: str = Query(default="1h"),
    strategy_id: str | None = Query(default=None),
    limit: int = Query(default=1500, ge=200, le=4000),
) -> dict:
    """Backtest one strategy (or all individual strategies) and store the runs."""
    symbol = symbol.upper()
    from strategies.registry import REGISTRY

    ids = [strategy_id] if strategy_id else [s for s in REGISTRY if s != "composite_sweep_mss_fvg_ob"]
    results: list[dict] = []
    for sid in ids:
        if sid not in REGISTRY:
            raise HTTPException(status_code=404, detail=f"unknown strategy {sid}")
        try:
            res = run_backtest_for(symbol, interval, sid, limit=limit)
        except HTTPException as exc:
            results.append({"strategy_id": sid, "error": exc.detail})
            continue
        results.append({
            "strategy_id": sid,
            "run_id": res["run_id"],
            "detections_found": res["detections_found"],
            "leakage_excluded": res["leakage_excluded"],
            "trades_total": res["trades_total"],
            "skipped_no_levels": res.get("skipped_no_levels", 0),
            "metrics": res["metrics"],
            "oos_metrics": res["oos_metrics"],
        })
    return {"symbol": symbol, "interval": interval, "results": results}


@router.get("/summary")
def summary(symbol: str = Query(default="XAUUSD"), interval: str = Query(default="1h")) -> dict:
    """Latest stored backtest run per strategy — the comparison table source."""
    symbol = symbol.upper()
    with get_pool().connection() as conn:
        cur = conn.execute(
            """
            SELECT DISTINCT ON (r.strategy_id)
                r.strategy_id, r.id AS run_id, r.data_start, r.data_end,
                r.metrics, r.oos_metrics, r.leakage_excluded, r.created_at
            FROM backtest_runs r
            WHERE r.symbol = %s AND r.interval = %s
            ORDER BY r.strategy_id, r.created_at DESC
            """,
            (symbol, interval.lower()),
        )
        rows = cur.fetchall()
    return {
        "symbol": symbol,
        "interval": interval.lower(),
        "strategies": [
            {
                "strategy_id": r["strategy_id"],
                "run_id": r["run_id"],
                "data_start": r["data_start"].isoformat()[:10] if r["data_start"] else None,
                "data_end": r["data_end"].isoformat()[:10] if r["data_end"] else None,
                "metrics": r["metrics"],
                "oos_metrics": r["oos_metrics"],
                "leakage_excluded": r["leakage_excluded"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ],
    }
