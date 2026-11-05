"""Missed Opportunity Analysis (enhancement spec §10).

For every major gold move (|24h-forward return| ≥ threshold), answer:
  1. Was there a directional signal before the move?
  2. If a signal existed but wasn't actionable — why (WAIT/NO_TRADE/veto)?
  3. If no signal existed — which strategies had fired in the prior 24h?

Deterministic over persisted data only. Never claims "would have made X" —
records coverage and blocking reasons so improvements can be evidence-based.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db import get_pool

MOVE_THRESHOLD_PCT = 1.5
LOOKBACK_HOURS = 24
STRIDE_HOURS = 12  # dedupe overlapping major moves


def _signals_before(conn, symbol: str, interval: str, t: datetime):
    cur = conn.execute(
        """
        SELECT id, signal_type, created_at, price, score, invalidation_level, note
        FROM trading_signals
        WHERE symbol = %s AND interval = %s
          AND created_at >= %s AND created_at <= %s
          AND signal_type IN ('BUY','STRONG_BUY','SELL','STRONG_SELL','EARLY_BUY','EARLY_SELL','WAIT','NO_TRADE')
        ORDER BY created_at DESC LIMIT 1
        """,
        (symbol, interval, t - timedelta(hours=LOOKBACK_HOURS), t),
    )
    return cur.fetchone()


def _detections_before(conn, symbol: str, interval: str, t: datetime):
    cur = conn.execute(
        """
        SELECT d.strategy_id, d.direction, d.anchor_time
        FROM strategy_detections d
        JOIN instruments i ON i.id = d.instrument_id
        WHERE i.symbol = %s AND d.interval = %s
          AND d.anchor_time >= %s AND d.anchor_time <= %s
        ORDER BY d.anchor_time DESC LIMIT 30
        """,
        (symbol, interval, t - timedelta(hours=LOOKBACK_HOURS), t),
    )
    return cur.fetchall()


def scan_missed(symbol: str, interval: str, lookback_days: int = 30) -> dict:
    symbol = symbol.upper()
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=lookback_days)
    with get_pool().connection() as conn:
        inst = conn.execute("SELECT id FROM instruments WHERE symbol = %s", (symbol,)).fetchone()
        if inst is None:
            return {"error": f"unknown instrument {symbol}"}
        candles = conn.execute(
            """
            SELECT market_ts, close FROM market_candles
            WHERE instrument_id = %s AND interval = %s AND market_ts >= %s
            ORDER BY market_ts
            """,
            (inst["id"], interval, cutoff - timedelta(hours=LOOKBACK_HOURS)),
        ).fetchall()
        rows = [(r["market_ts"], float(r["close"])) for r in candles]

    # major moves: |forward 24h return| ≥ threshold, deduped by stride
    moves: list[tuple[datetime, float, str]] = []  # (bar time, fwd return %, direction)
    last_recorded: datetime | None = None
    closes_by_time = dict(rows)
    for ts, close in rows:
        if ts < cutoff or ts > now - timedelta(hours=LOOKBACK_HOURS):
            continue
        target = ts + timedelta(hours=LOOKBACK_HOURS)
        # nearest candle at/after target
        fwd = next((c for t2, c in rows if t2 >= target), None)
        if fwd is None:
            continue
        ret = (fwd - close) / close * 100
        if abs(ret) < MOVE_THRESHOLD_PCT:
            continue
        if last_recorded and (ts - last_recorded) < timedelta(hours=STRIDE_HOURS):
            continue
        moves.append((ts, ret, "up" if ret > 0 else "down"))
        last_recorded = ts

    recorded = 0
    with get_pool().connection() as conn:
        for ts, ret, direction in moves:
            sig = _signals_before(conn, symbol, interval, ts)
            dets = _detections_before(conn, symbol, interval, ts)
            detected_by = sorted({d["strategy_id"] for d in dets})
            if sig is None:
                blocked = "no_signal_in_window"
            elif sig["signal_type"] in ("BUY", "STRONG_BUY", "SELL", "STRONG_SELL", "EARLY_BUY", "EARLY_SELL"):
                same_dir = (direction == "up" and sig["signal_type"] in ("BUY", "STRONG_BUY", "EARLY_BUY")) or (
                    direction == "down" and sig["signal_type"] in ("SELL", "STRONG_SELL", "EARLY_SELL")
                )
                blocked = "covered_by_signal" if same_dir else "signal_opposite"
            elif sig["signal_type"] == "WAIT":
                blocked = "signal_wait"
            else:
                blocked = "signal_no_trade"
            if blocked == "covered_by_signal":
                continue  # not missed
            conn.execute(
                """
                INSERT INTO missed_opportunities
                    (symbol, interval, move_time, move_pct, direction, signal_id, detected_by, blocked_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, interval, move_time) DO UPDATE SET
                    detected_by = EXCLUDED.detected_by, blocked_by = EXCLUDED.blocked_by,
                    signal_id = EXCLUDED.signal_id
                """,
                (symbol, interval, ts, round(ret, 3), direction,
                 sig["id"] if sig else None, __import__("json").dumps(detected_by), blocked),
            )
            recorded += 1
    return {"symbol": symbol, "interval": interval, "moves_found": len(moves), "missed_recorded": recorded}
