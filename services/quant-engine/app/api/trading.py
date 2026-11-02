"""Trading intelligence API: setups, alerts, paper trading."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app import alerts, paper, risk
from app.db import get_pool
from app.marketdata import store
from strategies import engine as strategy_engine

router = APIRouter(prefix="/v1", tags=["trading"])


# ----------------------------------------------------------- trade setups ---


@router.post("/strategies/evaluate_setups")
def evaluate_setups(symbol: str = Query(default="XAUUSD"), interval: str = "1h") -> dict:
    """Build + validate trade setups from recent composite detections."""
    symbol = symbol.upper()
    dets = strategy_engine.recent_detections(symbol, interval, 20)
    atr = risk._atr(symbol)
    created, rejected = [], []
    with get_pool().connection() as conn:
        inst = store.get_instrument_by_symbol(conn, symbol)
        if inst is None:
            raise HTTPException(status_code=404, detail=f"unknown instrument {symbol}")
        for det in dets:
            cand = risk.candidate_from_detection(det, atr)
            if cand is None:
                continue
            valid, reasons, size = risk.validate(cand, symbol)
            cur = conn.execute(
                """
                INSERT INTO trade_setups
                    (detection_id, instrument_id, direction, entry_low, entry_high, stop,
                     target1, target2, target3, risk_reward, position_size,
                     validation_status, validation_reasons, risk_engine_version, anchor_time)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (detection_id, risk_engine_version) DO NOTHING
                RETURNING id
                """,
                (
                    cand.detection_id, inst["id"], cand.direction,
                    cand.entry_low, cand.entry_high, cand.stop,
                    cand.target1, cand.target2, cand.target3,
                    abs(cand.target1 - cand.entry_low if cand.direction == "long" else cand.entry_high)
                    / max(1e-9, abs(cand.entry_low if cand.direction == "long" else cand.entry_high - cand.stop)),
                    size,
                    "valid" if valid else "rejected",
                    json.dumps(reasons),
                    risk.RISK_ENGINE_VERSION,
                    cand.anchor_time,
                ),
            )
            row = cur.fetchone()
            entry = {"id": row["id"] if row else None, "valid": valid, "reasons": reasons, "size": size}
            (created if valid else rejected).append(entry)
    return {"symbol": symbol, "valid_created": len(created), "rejected": rejected, "created": created}


@router.get("/setups")
def list_setups(symbol: str = Query(default="XAUUSD"), limit: int = Query(default=20, ge=1, le=100)) -> dict:
    symbol = symbol.upper()
    with get_pool().connection() as conn:
        inst = store.get_instrument_by_symbol(conn, symbol)
        if inst is None:
            raise HTTPException(status_code=404, detail=f"unknown instrument {symbol}")
        cur = conn.execute(
            """
            SELECT s.*, d.strategy_id, d.evidence
            FROM trade_setups s
            JOIN strategy_detections d ON d.id = s.detection_id
            WHERE s.instrument_id = %s
            ORDER BY s.anchor_time DESC LIMIT %s
            """,
            (inst["id"], limit),
        )
        rows = cur.fetchall()
    return {
        "count": len(rows),
        "setups": [
            {
                "id": r["id"],
                "strategy_id": r["strategy_id"],
                "direction": r["direction"],
                "entry_zone": [str(r["entry_low"]), str(r["entry_high"])],
                "stop": str(r["stop"]),
                "targets": [str(r["target1"]), str(r["target2"]) if r["target2"] else None,
                            str(r["target3"]) if r["target3"] else None],
                "risk_reward": str(r["risk_reward"]),
                "position_size": str(r["position_size"]) if r["position_size"] else None,
                "validation_status": r["validation_status"],
                "validation_reasons": r["validation_reasons"],
                "anchor_time": r["anchor_time"].isoformat() if r["anchor_time"] else None,
                "evidence": (r["evidence"] or [])[:3],
            }
            for r in rows
        ],
    }


class PaperOpenRequest(BaseModel):
    symbol: str = "XAUUSD"
    direction: str  # long | short
    size: float | None = None      # oz; if omitted, risk-based sizing needs stop
    stop: float | None = None
    target: float | None = None
    setup_id: int | None = None
    account_id: int | None = None


# --------------------------------------------------------------- paper ---


@router.get("/paper/accounts")
def accounts() -> dict:
    aid = paper.ensure_default_account()
    return paper.account_summary(aid)


@router.post("/paper/trades")
def open_paper_trade(req: PaperOpenRequest) -> dict:
    symbol = req.symbol.upper()
    if req.direction not in ("long", "short"):
        raise HTTPException(status_code=400, detail="direction must be long|short")
    aid = req.account_id or paper.ensure_default_account()
    try:
        size = req.size
        if size is None:
            if req.stop is None:
                raise HTTPException(status_code=400, detail="provide size or stop (for risk-based sizing)")
            with get_pool().connection() as conn:
                inst = store.get_instrument_by_symbol(conn, symbol)
                q = store.get_latest_quote(conn, inst["id"]) if inst else None
            entry = float(q["price"]) if q and q["price"] else None
            if entry is None:
                raise HTTPException(status_code=409, detail="no fresh quote for sizing")
            preview = risk.position_preview(symbol, entry, req.stop)
            size = preview["position_size"]
            if size <= 0:
                raise HTTPException(status_code=400, detail="sizing rounds to zero")
        trade = paper.open_trade(aid, symbol, req.direction, size, req.stop, req.target, req.setup_id)
        return {"opened": True, "trade": trade, "simulated": True}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/paper/trades")
def list_paper_trades(status: str = Query(default="all")) -> dict:
    aid = paper.ensure_default_account()
    summary = paper.account_summary(aid)
    trades = summary["open_positions"] if status == "open" else (
        summary["closed_trades"] if status == "closed" else summary["open_positions"] + summary["closed_trades"]
    )
    return {"count": len(trades), "trades": trades}


@router.post("/paper/trades/{trade_id}/close")
def close_paper_trade(trade_id: int, reason: str = "manual") -> dict:
    try:
        return {"closed": True, "trade": paper.close_trade(trade_id, reason), "simulated": True}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/paper/monitor")
def monitor() -> dict:
    return paper.monitor_open_trades()


# --------------------------------------------------------------- alerts ---


class AlertRuleRequest(BaseModel):
    kind: str
    symbol: str = "XAUUSD"
    params: dict = {}
    severity: str = "info"
    cooldown_seconds: int = 3600


@router.get("/alerts")
def list_alert_rules() -> dict:
    return {"rules": alerts.list_rules(), "recent_events": alerts.recent_events(20)}


@router.post("/alerts")
def create_alert(req: AlertRuleRequest) -> dict:
    if req.kind not in ("price_above", "price_below", "sweep", "fvg", "bos_choch", "setup_new", "analysis_new"):
        raise HTTPException(status_code=400, detail="unknown alert kind")
    if req.severity not in ("info", "warning", "critical"):
        raise HTTPException(status_code=400, detail="severity must be info|warning|critical")
    return alerts.create_rule(req.kind, req.symbol, req.params, req.severity, req.cooldown_seconds)


@router.delete("/alerts/{rule_id}")
def delete_alert(rule_id: int) -> dict:
    if not alerts.delete_rule(rule_id):
        raise HTTPException(status_code=404, detail="rule not found")
    return {"deleted": True}


@router.post("/alerts/evaluate")
def evaluate_alerts() -> dict:
    return alerts.evaluate_all()
