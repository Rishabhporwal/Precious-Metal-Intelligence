"""Signal-rule backtest (enhancement follow-up): replay the DETERMINISTIC
signal rules over stored history and grade hypothetical decisions with the
pessimistic fill model.

Honest scope (labeled in every result):
  - TECHNICAL-ONLY: verdicts come from the 33 strategies + regime. Historical
    news sentiment cannot be reconstructed, so the news vote and the news
    event veto are ABSENT for most of the window (event veto applied only
    where economic_events rows exist). Results will overstate aggression vs
    live, never understate it — treat as a threshold sanity check.
  - MODEL-BASED ESTIMATES: pessimistic fills — entry at next bar open ± spread,
    intrabar stop+target ambiguity → STOP wins, gap past stop → open fill,
    50% out at T1 then stop to breakeven, remainder at T2/BE, expiry at close.
  - Decisions are evaluated on data prefixes only (no lookahead): at grid
    time t every strategy sees candles up to t, exactly as live.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from app.db import get_pool
from indicators.oscillators import atr
from quant.regimes import regime_report
from signals.engine import decide
from strategies import verdicts as sv
from strategies.base import build_context
from strategies.registry import REGISTRY

SPREAD = 0.4          # XAUUSD typical spread, $/oz
STOP_ATR_MULT = 1.5
EXPIRY_BARS = 24
WARMUP = 320          # strategies see up to this many bars of prefix


def _grade_trade(side: str, entry: float, stop: float, t1: float, t2: float, fwd: list[dict]) -> dict:
    """Pessimistic walk-forward grading. Returns R-multiple components."""
    open_stop = stop
    leg1_done = leg2_done = False
    r1 = r2 = None
    for bar in fwd[: EXPIRY_BARS + 1]:
        o, h, l = float(bar["open"]), float(bar["high"]), float(bar["low"])
        if side == "long":
            stop_hit = l <= open_stop
            gap_fill = o <= open_stop
            t1_hit = h >= t1
            t2_hit = h >= t2
        else:
            stop_hit = h >= open_stop
            gap_fill = o >= open_stop
            t1_hit = l <= t1
            t2_hit = l <= t2
        exit_stop = gap_fill and stop_hit
        if not leg1_done:
            if exit_stop:
                fill = o if gap_fill else open_stop
                r1 = (fill - entry) / (entry - stop) if side == "long" else (entry - fill) / (stop - entry)
                r2 = r1  # remainder stopped too (never reached T1)
                leg1_done = leg2_done = True
                break
            if t1_hit:
                r1 = 1.0
                leg1_done = True
                open_stop = entry  # stop to breakeven
        else:
            if exit_stop:
                fill = o if gap_fill else open_stop
                r2 = 0.0 if abs(open_stop - entry) < 1e-9 else (
                    (fill - entry) / (entry - stop) if side == "long" else (entry - fill) / (stop - entry))
                leg2_done = True
                break
            if t2_hit:
                r2 = 2.0
                leg2_done = True
                break
    if r1 is None:  # expired without T1
        last = float(fwd[EXPIRY_BARS]["close"]) if len(fwd) > EXPIRY_BARS else None
        if last is None:
            return {"r": None}
        r = (last - entry) / (entry - stop) if side == "long" else (entry - last) / (stop - entry)
        return {"r": round(r, 3), "exit": "expired"}
    if not leg2_done:  # T1 hit, remainder still running at window end
        if len(fwd) > EXPIRY_BARS:
            last = float(fwd[EXPIRY_BARS]["close"])
            r2 = 0.0 if abs(open_stop - entry) < 1e-9 else (
                (last - open_stop) / (entry - stop) if side == "long" else (open_stop - last) / (stop - entry))
            r2 = max(r2, 0.0) if abs(open_stop - entry) < 1e-9 else r2
        else:
            return {"r": None}
    return {"r": round(0.5 * (r1 or 0.0) + 0.5 * (r2 or 0.0), 3), "leg1_r": r1, "leg2_r": r2}


def run_signal_backtest(symbol: str, interval: str = "1h", days: int = 30, step_hours: int = 4) -> dict:
    symbol = symbol.upper()
    now = datetime.now(UTC)
    start = now - timedelta(days=days)
    with get_pool().connection() as conn:
        inst = conn.execute("SELECT id FROM instruments WHERE symbol = %s", (symbol,)).fetchone()
        if inst is None:
            return {"error": f"unknown instrument {symbol}"}
        rows_all = conn.execute(
            "SELECT market_ts, open, high, low, close FROM market_candles WHERE instrument_id = %s AND interval = %s AND market_ts >= %s ORDER BY market_ts",
            (inst["id"], interval, start - timedelta(days=20)),
        ).fetchall()
        daily_all = conn.execute(
            "SELECT market_ts, open, high, low, close FROM market_candles WHERE instrument_id = %s AND interval = '1day' ORDER BY market_ts",
            (inst["id"],),
        ).fetchall()

    grid = [r["market_ts"] for r in rows_all if r["market_ts"] >= start]
    grid = grid[:: max(step_hours // 1, 1)]
    trades: list[dict] = []
    eval_points = 0
    open_trade: dict | None = None
    decision_bar_idx = {r["market_ts"]: i for i, r in enumerate(rows_all)}

    for t in grid:
        if open_trade and open_trade["exit_due"] <= t:
            open_trade = None
        if open_trade:
            continue
        idx = decision_bar_idx.get(t)
        if idx is None or idx < WARMUP:
            continue
        prefix = rows_all[max(0, idx - WARMUP + 1) : idx + 1]
        daily_prefix = [d for d in daily_all if d["market_ts"] <= t][-60:]
        hourly_prefix = prefix[-72:]
        ctx = build_context(symbol, interval, prefix, daily_prefix, hourly_prefix)
        price = float(prefix[-1]["close"])

        verdicts = []
        for sid, cls in REGISTRY.items():
            try:
                dets = cls().detect(ctx)
            except Exception:  # noqa: BLE001 — mirror live behaviour
                continue
            dlist = [
                {"direction": d.direction, "anchor_time": d.anchor_time, "status": d.status}
                for d in dets
            ]
            verdicts.append(
                sv.classify(sid, cls.name if hasattr(cls, "name") else sid, dlist, price, interval, len(prefix), now=t)
            )
        regime = regime_report(
            [float(r["close"]) for r in prefix], [float(r["high"]) for r in prefix], [float(r["low"]) for r in prefix]
        )
        decision = decide(verdicts, regime, event_veto=False, veto_events=[], price=price,
                          prev_open_signal=None, plan_levels=None, interval=interval, now=t)
        eval_points += 1
        st = decision.get("signal_type")
        if st not in ("EARLY_BUY", "BUY", "STRONG_BUY", "EARLY_SELL", "SELL", "STRONG_SELL"):
            continue

        side = "long" if "BUY" in st else "short"
        # entry at NEXT bar open (no lookahead fill), plus spread cost
        nxt = rows_all[idx + 1] if idx + 1 < len(rows_all) else None
        if nxt is None:
            continue
        entry = float(nxt["open"]) + (SPREAD if side == "long" else -SPREAD)
        a = atr([float(r["high"]) for r in prefix], [float(r["low"]) for r in prefix], [float(r["close"]) for r in prefix])
        atr14 = float(a[-1]) if a and a[-1] is not None else 0.0
        if atr14 <= 0:
            continue
        stop_dist = STOP_ATR_MULT * atr14
        stop = entry - stop_dist if side == "long" else entry + stop_dist
        t1 = entry + stop_dist if side == "long" else entry - stop_dist
        t2 = entry + 2 * stop_dist if side == "long" else entry - 2 * stop_dist
        fwd_start = idx + 1
        graded = _grade_trade(side, entry, stop, t1, t2, rows_all[fwd_start : fwd_start + EXPIRY_BARS + 2])
        trades.append({
            "decision_time": t.isoformat(), "signal_type": st, "score": decision["score"],
            "side": side, "entry": round(entry, 2), "stop": round(stop, 2),
            **({"r": graded["r"], "exit": graded.get("exit", "targets")} if graded.get("r") is not None else {"r": None}),
        })
        open_trade = {"exit_due": t + timedelta(hours=EXPIRY_BARS)}

    from backtesting.metrics import compute_metrics

    completed = [t for t in trades if t.get("r") is not None]
    metrics = (
        compute_metrics([
            {"r_multiple": t["r"], "exit_price": t["entry"], "pnl": t["r"] * 10.0, "direction": t["side"]}
            for t in completed
        ])
        if completed
        else {}
    )
    result = {
        "symbol": symbol,
        "interval": interval,
        "window_days": days,
        "step_hours": step_hours,
        "eval_points": eval_points,
        "signals": len(trades),
        "graded": len(completed),
        "metrics": metrics,
        "trades": trades[-20:],
        "scope": "TECHNICAL-ONLY (no historical news sentiment/veto) — model-based estimates, pessimistic fills, prefix-only evaluation",
    }
    with get_pool().connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO backtest_runs (symbol, interval, strategy_id, algo_version, params, cost_model,
                                       data_start, data_end, metrics)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (symbol, interval, "signal_engine_rules", "sig-bt-1", json.dumps({"step_hours": step_hours, "days": days}),
             json.dumps({"spread": SPREAD, "stop_atr": STOP_ATR_MULT, "fill_model": "pessimistic"}),
             start, now, json.dumps(metrics, default=str)),
        )
        result["run_id"] = int(cur.fetchone()["id"])
    return result
