"""Backtesting API: run + history."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.db import get_pool
from app.marketdata import store
from backtesting.engine import run_backtest
from providers.base import CandleInterval

router = APIRouter(prefix="/v1/backtests", tags=["backtesting"])


class BacktestRequest(BaseModel):
    symbol: str = "XAUUSD"
    interval: str = "1h"
    strategy_id: str = "composite_sweep_mss_fvg_ob"
    spread: float = 0.35
    slippage: float = 0.05
    max_wait_bars: int = 40
    oos_fraction: float = 0.4


@router.post("")
def run(req: BacktestRequest) -> dict:
    symbol = req.symbol.upper()
    with get_pool().connection() as conn:
        inst = store.get_instrument_by_symbol(conn, symbol)
        if inst is None:
            raise HTTPException(status_code=404, detail=f"unknown instrument {symbol}")
        if not inst["enabled"]:
            raise HTTPException(status_code=409, detail=f"instrument {symbol} is not enabled")
        rows = store.get_candles(conn, inst["id"], CandleInterval(req.interval), limit=4000)
        daily = store.get_candles(conn, inst["id"], CandleInterval.DAY_1, limit=400)
        hourly = store.get_candles(conn, inst["id"], CandleInterval.HOUR_1, limit=72)

    result = run_backtest(
        symbol, req.interval, req.strategy_id, rows=rows, daily=daily, hourly=hourly,
        costs={"spread": req.spread, "slippage": req.slippage},
        max_wait_bars=req.max_wait_bars, oos_fraction=req.oos_fraction,
    )
    if "error" in result:
        raise HTTPException(status_code=409, detail=result["error"])

    with get_pool().connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO backtest_runs
                (symbol, interval, strategy_id, algo_version, params, cost_model,
                 data_start, data_end, metrics, oos_metrics, leakage_excluded)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                symbol, req.interval, req.strategy_id, result.get("algo_version") or "",
                json.dumps({}), json.dumps(result["cost_model"]),
                result["data_start"], result["data_end"],
                json.dumps(result["metrics"]), json.dumps(result["oos_metrics"]),
                result["leakage_excluded"],
            ),
        )
        run_id = int(cur.fetchone()["id"])
        for t in result["trades"]:
            if t["exit_reason"] == "no_fill":
                continue
            conn.execute(
                """
                INSERT INTO backtest_trades
                    (run_id, direction, entry_time, exit_time, entry_price, exit_price,
                     stop, r_multiple, pnl, costs, exit_reason, segment)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    run_id, t["direction"], t["entry_time"], t["exit_time"],
                    t["entry_price"], t["exit_price"], t["stop"], t["r_multiple"],
                    t["pnl"], t["costs"], t["exit_reason"],
                    "oos" if t["entry_time"] >= conn.execute(
                        """
                        SELECT data_start + (data_end - data_start) * %s AS split_time
                        FROM backtest_runs WHERE id = %s
                        """,
                        (req.oos_fraction, run_id),
                    ).fetchone()["split_time"] else "is",
                ),
            )

    return {"run_id": run_id, **{k: v for k, v in result.items() if k != "trades"},
            "trades": result["trades"][:20]}


@router.get("")
def history(symbol: str = Query(default="XAUUSD"), limit: int = Query(default=10, ge=1, le=50)) -> dict:
    symbol = symbol.upper()
    with get_pool().connection() as conn:
        cur = conn.execute(
            """
            SELECT id, symbol, interval, strategy_id, data_start, data_end,
                   metrics, oos_metrics, leakage_excluded, created_at
            FROM backtest_runs WHERE symbol = %s
            ORDER BY created_at DESC LIMIT %s
            """,
            (symbol, limit),
        )
        rows = cur.fetchall()
    return {
        "count": len(rows),
        "runs": [
            {
                "id": r["id"], "interval": r["interval"], "strategy_id": r["strategy_id"],
                "data_start": r["data_start"].isoformat() if r["data_start"] else None,
                "data_end": r["data_end"].isoformat() if r["data_end"] else None,
                "metrics": r["metrics"],
                "oos_metrics": r["oos_metrics"],
                "leakage_excluded": r["leakage_excluded"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ],
    }


@router.get("/{run_id}")
def get_run(run_id: int) -> dict:
    with get_pool().connection() as conn:
        cur = conn.execute("SELECT * FROM backtest_runs WHERE id = %s", (run_id,))
        run_row = cur.fetchone()
        if run_row is None:
            raise HTTPException(status_code=404, detail="run not found")
        trades = conn.execute(
            "SELECT * FROM backtest_trades WHERE run_id = %s ORDER BY entry_time", (run_id,)
        ).fetchall()
    return {
        **{k: run_row[k] for k in ("id", "symbol", "interval", "strategy_id", "algo_version",
                                    "params", "cost_model", "metrics", "oos_metrics",
                                    "leakage_excluded")},
        "data_start": run_row["data_start"].isoformat() if run_row["data_start"] else None,
        "data_end": run_row["data_end"].isoformat() if run_row["data_end"] else None,
        "trades": [
            {
                "direction": t["direction"], "entry_time": t["entry_time"].isoformat(),
                "exit_time": t["exit_time"].isoformat() if t["exit_time"] else None,
                "r_multiple": str(t["r_multiple"]) if t["r_multiple"] else None,
                "pnl": str(t["pnl"]) if t["pnl"] else None,
                "exit_reason": t["exit_reason"], "segment": t["segment"],
            }
            for t in trades
        ],
    }
