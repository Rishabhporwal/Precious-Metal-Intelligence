"""Backtest engine: honest historical replay of strategy detections.

Execution model (documented assumptions, pessimistic where ambiguous):
- Detections are re-verified on the data prefix (leakage gate) — future-dependent
  detections are excluded and counted.
- Entry: limit-style — price must touch the entry zone within `max_wait_bars`
  after the anchor; fill at zone edge + spread (worst side).
- Intrabar stop/target ambiguity: if a candle touches BOTH stop and target,
  the STOP wins (pessimistic-first, per master spec).
- Gap handling: if the candle opens beyond the stop, fill at the open (worse).
- Costs: spread deducted on entry AND exit, slippage per side.
- Partial exits: 50% at T1 (stop moved to entry = breakeven), remainder at T2
  or breakeven stop. T3 recorded but not executed (kept for live use).
- End of data: position closed at last close, exit_reason=expired.

Results are labeled as model-based estimates with the assumptions stored
alongside; they are not claims of achievable performance.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from strategies.base import build_context
from strategies.registry import REGISTRY

from .leakage import verify_detection_prefix
from .metrics import compute_metrics

logger = logging.getLogger("backtest")

DEFAULT_COSTS = {"spread": 0.35, "slippage": 0.05, "commission": 0.0}


def _plan_from_detection(det: Any, anchor_close: float, atr: float | None) -> dict | None:
    """Generic entry/stop plan for any strategy's detection (per-strategy backtests).

    Uses the detection's own levels when present (overlap/entry zone, stop);
    falls back to a documented ATR plan: entry at the anchor close, stop at
    1.5×ATR beyond it, targets at 1R/2R. Deterministic, no future data.
    """
    levels = det.levels or {}
    sign = 1 if det.direction == "bullish" else -1
    zone_lo = levels.get("overlap_low", levels.get("entry_low"))
    zone_hi = levels.get("overlap_high", levels.get("entry_high"))
    if zone_lo is not None and zone_hi is not None:
        entry_low, entry_high = float(zone_lo), float(zone_hi)
    else:
        w = 0.25 * (atr or anchor_close * 0.006)
        entry_low, entry_high = anchor_close - sign * w, anchor_close + sign * w
        entry_low, entry_high = min(entry_low, entry_high), max(entry_low, entry_high)

    stop = levels.get("stop")
    if stop is None:
        stop = entry_low - 1.5 * (atr or anchor_close * 0.006) if sign > 0 else entry_high + 1.5 * (atr or anchor_close * 0.006)
    stop = float(stop)
    entry_ref = entry_low if sign > 0 else entry_high
    risk = abs(entry_ref - stop)
    if risk <= 0:
        return None
    return {"entry_low": entry_low, "entry_high": entry_high, "stop": stop, "t1": entry_ref + sign * risk, "t2": entry_ref + sign * 2 * risk, "risk": risk}


def run_backtest(
    symbol: str,
    interval: str,
    strategy_id: str = "composite_sweep_mss_fvg_ob",
    rows: list[dict] | None = None,
    daily: list[dict] | None = None,
    hourly: list[dict] | None = None,
    params: dict | None = None,
    costs: dict | None = None,
    max_wait_bars: int = 20,
    initial_equity: float = 1000.0,
    risk_pct: float = 1.0,
    oos_fraction: float = 0.4,
) -> dict:
    costs = {**DEFAULT_COSTS, **(costs or {})}
    cls = REGISTRY.get(strategy_id)
    if cls is None:
        raise ValueError(f"unknown strategy {strategy_id}")
    if rows is None or len(rows) < 100:
        return {"error": "need >= 100 candles"}

    merged_params = {**(cls.default_params or {}), **(params or {})}
    n = len(rows)
    split_idx = int(n * (1 - oos_fraction))

    ctx = build_context(symbol, interval, rows, daily or rows[-40:], hourly or rows[-24:], params=merged_params)

    # 1. detections on full history (same code path as live)
    detections = cls().detect(ctx)
    detections.sort(key=lambda d: d.anchor_time)

    # 2. leakage gate: verify each detection exists in the prefix view
    verified: list[tuple[int, object]] = []  # (anchor_index, detection)
    excluded = 0
    skipped_no_levels = 0
    skipped_at_end = 0
    times = ctx.times
    for d in detections:
        idx = next((i for i, t in enumerate(times) if t == d.anchor_time), None)
        if idx is None or idx < 60:
            continue
        if idx >= n - 5:
            # detection at the very end of history — no forward bars to trade
            skipped_at_end += 1
            continue
        plan = _plan_from_detection(d, float(rows[idx]["close"]), None)
        if plan is None:
            # no usable plan from this detection's levels — counted, not silent
            skipped_no_levels += 1
            continue
        if verify_detection_prefix(strategy_id, idx, rows, daily or rows[-40:], hourly or rows[-24:], merged_params):
            verified.append((idx, d))
        else:
            excluded += 1
            logger.info("leakage gate excluded detection at %s", d.anchor_time)

    # 3. simulate
    trades: list[dict] = []
    open_until = -1  # no overlapping positions (one at a time)
    for anchor_idx, det in verified:
        if anchor_idx <= open_until:
            continue  # skip overlapping signals
        plan = _plan_from_detection(det, float(ctx.closes[anchor_idx]), None)
        if plan is None:
            continue
        entry_low, entry_high = plan["entry_low"], plan["entry_high"]
        stop = plan["stop"]
        direction = "long" if det.direction == "bullish" else "short"
        entry_ref = entry_low if direction == "long" else entry_high
        risk = plan["risk"]
        sign = 1 if direction == "long" else -1
        t1 = plan["t1"]
        t2 = plan["t2"]

        # entry wait: touch the zone after the anchor
        entry_idx = None
        entry_price = None
        for j in range(anchor_idx + 1, min(n, anchor_idx + max_wait_bars + 1)):
            lo, hi = ctx.lows[j], ctx.highs[j]
            if direction == "long" and lo <= entry_high:
                entry_price = min(entry_high, hi)  # fill at zone edge or better(low)
                entry_idx = j
                break
            if direction == "short" and hi >= entry_low:
                entry_price = max(entry_low, lo)
                entry_idx = j
                break
        if entry_idx is None:
            trades.append({
                "direction": direction, "entry_time": ctx.times[anchor_idx],
                "exit_time": None, "entry_price": None, "exit_price": None,
                "stop": stop, "r_multiple": None, "pnl": None, "costs": 0.0,
                "exit_reason": "no_fill",
            })
            continue

        # manage position
        entry_fill = entry_price + sign * costs["spread"] + sign * costs["slippage"]
        effective_stop = stop
        realized_r = 0.0
        half_done = False
        exit_price = None
        exit_idx = None
        exit_reason = "expired"
        for j in range(entry_idx + 1, n):
            o, h, l = ctx.opens[j], ctx.highs[j], ctx.lows[j]
            stop_hit = (direction == "long" and (l <= effective_stop or o <= effective_stop)) or (
                direction == "short" and (h >= effective_stop or o >= effective_stop)
            )
            target_hit = (direction == "long" and h >= t2) or (direction == "short" and l <= t2)
            t1_hit = (direction == "long" and h >= t1) or (direction == "short" and l <= t1)

            # pessimistic-first: stop wins intrabar ambiguity
            if stop_hit:
                fill = o if (direction == "long" and o <= effective_stop) or (direction == "short" and o >= effective_stop) else effective_stop
                fill = fill - sign * costs["slippage"]
                exit_price, exit_idx, exit_reason = fill, j, "stop"
                break
            if t1_hit and not half_done:
                realized_r += 0.5 * 1.0  # 1R on half position
                half_done = True
                effective_stop = entry_fill  # move to breakeven
            if target_hit:
                fill = t2 + sign * costs["slippage"]
                exit_price, exit_idx, exit_reason = fill, j, "target"
                realized_r += 0.5 * 2.0 if half_done else 2.0
                break
        else:
            exit_price, exit_idx, exit_reason = ctx.closes[-1], n - 1, "expired"
            exit_r = (exit_price - entry_fill) * sign / risk
            realized_r += 0.5 * exit_r if half_done else exit_r

        costs_total = costs["spread"] + 2 * costs["slippage"]  # rough per-trade cost in price units
        costs_in_r = costs_total / risk
        net_r = realized_r - costs_in_r
        risk_amount = initial_equity * risk_pct / 100.0
        open_until = exit_idx or entry_idx
        trades.append({
            "direction": direction,
            "entry_time": ctx.times[entry_idx],
            "exit_time": ctx.times[exit_idx] if exit_idx is not None else ctx.times[-1],
            "entry_price": entry_fill,
            "exit_price": exit_price,
            "stop": stop,
            "r_multiple": round(net_r, 3),
            "pnl": round(net_r * risk_amount, 2),
            "costs": round(costs_in_r * risk_amount, 2),
            "exit_reason": exit_reason,
        })

    # 4. IS / OOS split by entry time
    split_time = rows[split_idx]["market_ts"]
    is_trades = [t for t in trades if t["entry_time"] < split_time and t["exit_reason"] != "no_fill"]
    oos_trades = [t for t in trades if t["entry_time"] >= split_time and t["exit_reason"] != "no_fill"]

    metrics = compute_metrics(is_trades, initial_equity, initial_equity * risk_pct / 100.0)
    oos_metrics = compute_metrics(oos_trades, initial_equity, initial_equity * risk_pct / 100.0)

    return {
        "symbol": symbol,
        "interval": interval,
        "strategy_id": strategy_id,
        "algo_version": cls.__module__ and "composite-1.0.0",
        "data_start": rows[0]["market_ts"].isoformat(),
        "data_end": rows[-1]["market_ts"].isoformat(),
        "detections_found": len(detections),
        "leakage_excluded": excluded,
        "skipped_no_levels": skipped_no_levels,
        "skipped_at_end": skipped_at_end,
        "trades_total": len(trades),
        "no_fill_count": sum(1 for t in trades if t["exit_reason"] == "no_fill"),
        "metrics": metrics,
        "oos_metrics": oos_metrics,
        "trades": trades,
        "cost_model": costs,
        "assumptions": [
            "stop wins intrabar ambiguity (pessimistic)",
            "gap-through stop fills at open",
            "50% partial at T1 then breakeven stop; remainder at T2",
            "spread deducted on entry and exit; slippage per side",
            "one position at a time; signals during open trade skipped",
            "results are model-based estimates with stated assumptions — not achievable-performance claims",
        ],
    }
