"""Strategy engine: runs the registry over stored candles, persists detections
(append-only, deduplicated by unique constraint) and structure events."""

from __future__ import annotations

import json
import logging

from app.db import get_pool
from app.marketdata import store
from providers.base import CandleInterval
from strategies.base import ALGO_VERSION, Detection, build_context
from strategies.registry import REGISTRY

logger = logging.getLogger("strategies")

EVAL_INTERVALS = (CandleInterval.MIN_15, CandleInterval.HOUR_1, CandleInterval.DAY_1)

# strategies that need a counterpart series injected (SMT)
CROSS_MARKET = {"cross_market_smt": {"counterpart_symbol": "XAGUSD"}}


def _load_configs() -> dict[str, dict]:
    with get_pool().connection() as conn:
        cur = conn.execute("SELECT strategy_id, enabled, params FROM strategy_configs")
        return {r["strategy_id"]: {"enabled": r["enabled"], "params": r["params"]} for r in cur.fetchall()}


def _counterpart_rows(symbol: str, interval: str, limit: int = 500) -> list[dict]:
    with get_pool().connection() as conn:
        inst = store.get_instrument_by_symbol(conn, symbol)
        if inst is None:
            return []
        try:
            return store.get_candles(conn, inst["id"], CandleInterval(interval), limit=limit)
        except ValueError:
            return []


def run_evaluation(symbol: str, interval: CandleInterval, limit: int = 1500) -> dict:
    """Run all enabled strategies for one instrument+interval and persist results."""
    with get_pool().connection() as conn:
        instrument = store.get_instrument_by_symbol(conn, symbol)
        if instrument is None:
            raise ValueError(f"unknown instrument {symbol}")
        if not instrument["enabled"]:
            return {"symbol": symbol, "interval": interval.value, "detections": 0,
                    "skipped": "instrument not enabled"}
        rows = store.get_candles(conn, instrument["id"], interval, limit=limit)
        daily = store.get_candles(conn, instrument["id"], CandleInterval.DAY_1, limit=400)
        hourly = store.get_candles(conn, instrument["id"], CandleInterval.HOUR_1, limit=72)

    if len(rows) < 60:
        return {"symbol": symbol, "interval": interval.value, "detections": 0,
                "skipped": "insufficient candles"}

    configs = _load_configs()
    ctx = build_context(symbol.upper(), interval.value, rows, daily, hourly)

    # persist structure events (BOS/CHoCH) from the context
    with get_pool().connection() as conn:
        for ev in ctx.events:
            conn.execute(
                """
                INSERT INTO market_structure_events
                    (instrument_id, interval, kind, event_time, level, algo_version)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (instrument_id, interval, kind, event_time) DO NOTHING
                """,
                (instrument["id"], interval.value, ev.kind, ctx.times[ev.index], ev.level, ALGO_VERSION),
            )

    all_detections: list[Detection] = []
    for strategy_id, cls in REGISTRY.items():
        cfg = configs.get(strategy_id, {"enabled": True, "params": {}})
        if not cfg["enabled"]:
            continue
        params = {**(cls.default_params or {}), **(cfg.get("params") or {})}
        if strategy_id in CROSS_MARKET:
            counterpart_symbol = CROSS_MARKET[strategy_id]["counterpart_symbol"]
            params["counterpart_candles"] = _counterpart_rows(counterpart_symbol, interval.value)
        strategy = cls()
        try:
            dets = strategy.detect(ctx) if strategy_id not in CROSS_MARKET or params.get("counterpart_candles") else []
        except Exception as exc:  # noqa: BLE001 — one broken strategy must not kill the run
            logger.warning("strategy %s failed on %s %s: %s", strategy_id, symbol, interval.value, exc)
            continue
        all_detections.extend(dets)

    persisted = 0
    with get_pool().connection() as conn:
        for d in all_detections:
            cur = conn.execute(
                """
                INSERT INTO strategy_detections
                    (strategy_id, algo_version, instrument_id, interval, direction,
                     status, anchor_time, levels, evidence, params)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (strategy_id, instrument_id, interval, anchor_time) DO NOTHING
                """,
                (
                    d.strategy_id, d.algo_version, instrument["id"], d.interval,
                    d.direction, d.status, d.anchor_time,
                    json.dumps(d.levels, default=str),
                    json.dumps(d.evidence),
                    json.dumps(d.params, default=str),
                ),
            )
            persisted += cur.rowcount

    return {
        "symbol": symbol,
        "interval": interval.value,
        "strategies_run": sum(1 for s in REGISTRY if configs.get(s, {}).get("enabled", True)),
        "detections_found": len(all_detections),
        "detections_persisted": persisted,
    }


def list_strategies() -> list[dict]:
    configs = _load_configs()
    out = []
    for sid, cls in REGISTRY.items():
        cfg = configs.get(sid, {"enabled": True, "params": {}})
        out.append({
            "strategy_id": sid,
            "name": cls.name,
            "description": cls.description,
            "default_params": cls.default_params,
            "enabled": cfg["enabled"],
            "params_override": cfg["params"],
            "algo_version": ALGO_VERSION,
        })
    return out


def recent_detections(symbol: str, interval: str | None, limit: int = 50) -> list[dict]:
    with get_pool().connection() as conn:
        inst = store.get_instrument_by_symbol(conn, symbol)
        if inst is None:
            return []
        clauses = ["d.instrument_id = %s"]
        params: list = [inst["id"]]
        if interval:
            clauses.append("d.interval = %s")
            params.append(interval)
        params.append(limit)
        cur = conn.execute(
            f"""
            SELECT d.strategy_id, d.algo_version, d.interval, d.direction, d.status,
                   d.anchor_time, d.levels, d.evidence
            FROM strategy_detections d
            WHERE {" AND ".join(clauses)}
            ORDER BY d.anchor_time DESC
            LIMIT %s
            """,
            params,
        )
        return cur.fetchall()
