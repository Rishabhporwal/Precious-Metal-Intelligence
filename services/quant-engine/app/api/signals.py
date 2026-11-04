"""Trading signals API — generate, latest, history, grading, stats."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query

from ai.verdict import build_verdict
from app.api.strategy_verdicts import evaluate as evaluate_verdicts
from app.db import get_pool
from app.macrodata import upcoming_events
from app.marketdata import store
from providers.base import CandleInterval
from quant.regimes import regime_report
from signals.engine import decide, grade

router = APIRouter(prefix="/v1/signals", tags=["signals"])

DIRECTIONAL = ("BUY", "STRONG_BUY", "SELL", "STRONG_SELL", "EARLY_BUY", "EARLY_SELL")


@router.post("/generate")
def generate(symbol: str = Query(default="XAUUSD"), interval: str = Query(default="1h")) -> dict:
    symbol = symbol.upper()
    sv = evaluate_verdicts(symbol=symbol, interval=interval)  # fresh verdicts (persists snapshot)
    verdicts = sv["verdicts"]
    price = float(sv["price"])

    with get_pool().connection() as conn:
        inst = store.get_instrument_by_symbol(conn, symbol)
        assert inst is not None  # evaluate_verdicts already verified existence
        daily = store.get_candles(conn, inst["id"], CandleInterval.DAY_1, limit=300)
        hourly = store.get_candles(conn, inst["id"], CandleInterval.HOUR_1, limit=120)

    closes = [float(r["close"]) for r in hourly]
    highs = [float(r["high"]) for r in hourly]
    lows = [float(r["low"]) for r in hourly]
    regime = regime_report(closes, highs, lows)

    bv = build_verdict(
        symbol=symbol, quote_price=price, daily=daily, hourly=hourly,
        strategy_bias={"bullish": 0, "bearish": 0, "net": 0},
        events=upcoming_events(10, 1), news_net=None,
    )
    veto = bv["event_risk"]["veto"]
    veto_events = bv["event_risk"]["events"]

    # previous open directional signal (ungraded)
    with get_pool().connection() as conn:
        cur = conn.execute(
            """
            SELECT * FROM trading_signals
            WHERE symbol = %s AND interval = %s AND graded = false
              AND signal_type IN ('BUY','STRONG_BUY','SELL','STRONG_SELL','EARLY_BUY','EARLY_SELL')
            ORDER BY created_at DESC LIMIT 1
            """,
            (symbol, interval),
        )
        prev = cur.fetchone()

    decision = decide(
        verdicts=verdicts,
        regime=regime,
        event_veto=veto,
        veto_events=veto_events,
        price=price,
        prev_open_signal=dict(prev) if prev else None,
        plan_levels=bv.get("plan"),
        interval=interval,
    )

    with get_pool().connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO trading_signals
                (symbol, interval, signal_type, expires_at, price, score, regime, confidence,
                 drivers, plan, invalidation_level, regime_snapshot, strategy_relevance, note)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, created_at
            """,
            (
                symbol, interval, decision["signal_type"],
                decision.get("expires_at"), price, decision["score"], decision["regime"],
                decision["confidence"], json.dumps(decision["drivers"]),
                json.dumps(decision.get("plan")), decision.get("invalidation_level"),
                json.dumps(regime), json.dumps(decision.get("strategy_relevance", [])),
                decision.get("note"),
            ),
        )
        row = cur.fetchone()
        signal_id, created_at = int(row["id"]), row["created_at"]

    # grade any expired ungraded signals for this symbol/interval
    graded = grade_expired(symbol, interval)

    return {
        "signal_id": signal_id,
        "created_at": created_at.isoformat() if created_at else None,
        **{k: v for k, v in decision.items() if k not in ("expires_at",)},
        "expires_at": decision.get("expires_at"),
        "key_levels": bv.get("key_levels"),
        "invalidations": bv.get("invalidations"),
        "graded_this_cycle": graded,
    }


def grade_expired(symbol: str, interval: str) -> int:
    """Grade ungraded signals whose expiry has passed (deterministic path walk)."""
    now = datetime.now(UTC)
    with get_pool().connection() as conn:
        cur = conn.execute(
            """
            SELECT id, signal_type, price, plan, invalidation_level, expires_at, created_at
            FROM trading_signals
            WHERE symbol = %s AND interval = %s AND graded = false
              AND signal_type IN ('BUY','STRONG_BUY','SELL','STRONG_SELL','EARLY_BUY','EARLY_SELL','WAIT')
              AND expires_at IS NOT NULL AND expires_at <= %s
            """,
            (symbol, interval, now),
        )
        due = cur.fetchall()
        if not due:
            return 0
        inst = store.get_instrument_by_symbol(conn, symbol)
        assert inst is not None
        candles = store.get_candles(conn, inst["id"], CandleInterval(interval), limit=300)
    count = 0
    for sig in due:
        t0 = sig["created_at"]
        highs = [float(r["high"]) for r in candles if r["market_ts"] > t0]
        lows = [float(r["low"]) for r in candles if r["market_ts"] > t0]
        closes = [float(r["close"]) for r in candles if r["market_ts"] > t0]
        outcome = grade(dict(sig), highs_after=highs, lows_after=lows, closes_after=closes)
        if not outcome.get("graded"):
            continue
        with get_pool().connection() as conn:
            conn.execute(
                """
                INSERT INTO signal_outcomes (signal_id, exit_reason, r_multiple, mfe, mae, direction_move_pct, detail)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    sig["id"], outcome.get("exit_reason"), outcome.get("r_multiple"),
                    outcome.get("mfe"), outcome.get("mae"), outcome.get("direction_move_pct"),
                    json.dumps(outcome),
                ),
            )
            conn.execute("UPDATE trading_signals SET graded = true WHERE id = %s", (sig["id"],))
        count += 1
    return count


@router.get("/latest")
def latest(symbol: str = Query(default="XAUUSD"), interval: str = Query(default="1h")) -> dict:
    symbol = symbol.upper()
    with get_pool().connection() as conn:
        cur = conn.execute(
            """
            SELECT s.*, o.exit_reason, o.r_multiple, o.mfe, o.mae
            FROM trading_signals s
            LEFT JOIN signal_outcomes o ON o.signal_id = s.id
            WHERE s.symbol = %s AND s.interval = %s
            ORDER BY s.created_at DESC LIMIT 1
            """,
            (symbol, interval),
        )
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="no signal yet — generate one")
    row = dict(row)
    for k in ("created_at", "expires_at"):
        if row.get(k):
            row[k] = row[k].isoformat()
    return row


@router.get("/history")
def history(
    symbol: str = Query(default="XAUUSD"),
    interval: str = Query(default="1h"),
    limit: int = Query(default=30, ge=1, le=200),
) -> dict:
    symbol = symbol.upper()
    with get_pool().connection() as conn:
        cur = conn.execute(
            """
            SELECT s.id, s.signal_type, s.created_at, s.expires_at, s.price, s.score,
                   s.regime, s.confidence, s.note, s.graded,
                   o.exit_reason, o.r_multiple
            FROM trading_signals s
            LEFT JOIN signal_outcomes o ON o.signal_id = s.id
            WHERE s.symbol = %s AND s.interval = %s
            ORDER BY s.created_at DESC LIMIT %s
            """,
            (symbol, interval, limit),
        )
        rows = cur.fetchall()
    return {
        "count": len(rows),
        "signals": [
            {
                "id": r["id"], "signal_type": r["signal_type"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "expires_at": r["expires_at"].isoformat() if r["expires_at"] else None,
                "price": r["price"], "score": r["score"], "regime": r["regime"],
                "confidence": r["confidence"], "note": r["note"], "graded": r["graded"],
                "exit_reason": r["exit_reason"], "r_multiple": r["r_multiple"],
            }
            for r in rows
        ],
    }


@router.get("/stats")
def stats(symbol: str = Query(default="XAUUSD"), interval: str = Query(default="1h")) -> dict:
    """Objective signal evaluation (enhancement spec §14): precision per signal type."""
    symbol = symbol.upper()
    with get_pool().connection() as conn:
        cur = conn.execute(
            """
            SELECT s.signal_type, count(*) AS n,
                   count(o.r_multiple) AS graded_n,
                   avg(o.r_multiple) FILTER (WHERE o.r_multiple IS NOT NULL) AS avg_r,
                   count(*) FILTER (WHERE o.r_multiple > 0) AS wins,
                   count(*) FILTER (WHERE o.r_multiple < 0) AS losses,
                   avg(o.mfe) FILTER (WHERE o.r_multiple IS NOT NULL) AS avg_mfe,
                   avg(o.mae) FILTER (WHERE o.r_multiple IS NOT NULL) AS avg_mae
            FROM trading_signals s
            LEFT JOIN signal_outcomes o ON o.signal_id = s.id
            WHERE s.symbol = %s AND s.interval = %s
              AND s.signal_type IN ('BUY','STRONG_BUY','SELL','STRONG_SELL','EARLY_BUY','EARLY_SELL','WAIT')
            GROUP BY s.signal_type ORDER BY s.signal_type
            """,
            (symbol, interval),
        )
        rows = cur.fetchall()
    out = []
    for r in rows:
        graded_n = int(r["graded_n"] or 0)
        wins = int(r["wins"] or 0)
        out.append({
            "signal_type": r["signal_type"],
            "total": int(r["n"]),
            "graded": graded_n,
            "avg_r": round(float(r["avg_r"]), 3) if r["avg_r"] is not None else None,
            "win_rate": round(wins / graded_n, 3) if graded_n else None,
            "avg_mfe_r": round(float(r["avg_mfe"]), 3) if r["avg_mfe"] is not None else None,
            "avg_mae_r": round(float(r["avg_mae"]), 3) if r["avg_mae"] is not None else None,
        })
    return {"symbol": symbol, "interval": interval, "stats": out}
