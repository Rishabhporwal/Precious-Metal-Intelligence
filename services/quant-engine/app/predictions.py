"""Prediction audit: every verdict plan is snapshotted at creation and graded
level-by-level as candles accrue — with a deterministic REASON for every
outcome. This is how we learn where the system is accurate and where it
needs work; no outcome is ever judged by memory, only by stored candles.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db import get_pool
from app.marketdata import store
from providers.base import CandleInterval

HORIZON_DAYS = 5


def snapshot_plan(verdict: dict, verdict_id: int) -> int | None:
    """Persist the freshly generated verdict plan as a pending prediction."""
    plan = verdict.get("plan") or {}
    if plan.get("stop") is None or plan.get("t1") is None:
        return None
    with get_pool().connection() as conn:
        # a newer plan supersedes the still-pending one — otherwise every
        # regeneration floods the audit with overlapping predictions that
        # expire unfilled and drown the real accuracy signal
        conn.execute(
            """
            UPDATE prediction_audit
            SET status = 'superseded', graded_at = now(),
                reason = 'Superseded: the engine regenerated the plan before this entry zone was ever touched.'
            WHERE symbol = %s AND status = 'pending'
            """,
            (verdict["symbol"],),
        )
        cur = conn.execute(
            """
            INSERT INTO prediction_audit
                (verdict_id, symbol, direction, mode, entry_low, entry_high,
                 stop, t1, t2, horizon_days)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                verdict_id, verdict["symbol"], verdict.get("direction") or "",
                (plan.get("mode") or "pullback"),
                plan.get("entry_low"), plan.get("entry_high"),
                plan.get("stop"), plan.get("t1"), plan.get("t2"), HORIZON_DAYS,
            ),
        )
        return int(cur.fetchone()["id"])


def grade_pending(symbol: str = "XAUUSD") -> int:
    """Grade every pending prediction whose horizon window is knowable."""
    symbol = symbol.upper()
    now = datetime.now(UTC)
    graded = 0
    with get_pool().connection() as conn:
        preds = conn.execute(
            """
            SELECT * FROM prediction_audit
            WHERE symbol = %s AND status = 'pending' AND created_at <= %s
            ORDER BY created_at
            """,
            (symbol, now - timedelta(hours=1)),  # give a fresh plan at least an hour
        ).fetchall()
        inst = conn.execute("SELECT id FROM instruments WHERE symbol = %s", (symbol,)).fetchone()
        if inst is None:
            return 0

        for p in preds:
            start = p["created_at"]
            end = start + timedelta(days=p["horizon_days"])
            if end > now:
                continue  # horizon not fully elapsed yet
            candles = store.get_candles(conn, inst["id"], CandleInterval.HOUR_1, limit=2000)
            fwd = [c for c in candles if start <= c["market_ts"] <= end]
            if len(fwd) < 12:
                continue  # not enough post-plan candles (sleep gap) — retry next cycle

            direction = p["direction"]
            el, eh = float(p["entry_low"]), float(p["entry_high"])
            stop, t1, t2 = float(p["stop"]), float(p["t1"]), float(p["t2"])

            # walk forward: entry fill, then stop vs targets in chronological order
            filled_at = t1_at = t2_at = stopped_at = None
            after_fill = None
            for c in fwd:
                h, l, ts = float(c["high"]), float(c["low"]), c["market_ts"]
                if filled_at is None:
                    if l <= eh and h >= el:  # zone touched
                        filled_at = ts
                    continue
                if after_fill is None:
                    after_fill = h if direction == "bearish" else l
                if direction == "bearish":
                    if h >= stop and stopped_at is None:
                        stopped_at = ts
                    if l <= t1 and t1_at is None and (stopped_at is None or ts <= stopped_at):
                        t1_at = ts
                    if l <= t2 and t2_at is None and t1_at is not None:
                        t2_at = ts
                else:
                    if l <= stop and stopped_at is None:
                        stopped_at = ts
                    if h >= t1 and t1_at is None and (stopped_at is None or ts <= stopped_at):
                        t1_at = ts
                    if h >= t2 and t2_at is None and t1_at is not None:
                        t2_at = ts

            # max favorable move after entry (how far the call went, $)
            fav = None
            if filled_at is not None:
                post = [c for c in fwd if c["market_ts"] >= filled_at]
                if direction == "bearish":
                    fav = eh - min((float(c["low"]) for c in post), default=eh)
                else:
                    fav = max((float(c["high"]) for c in post), default=el) - el

            # status + deterministic reason
            hours = lambda a, b: round((b - a).total_seconds() / 3600, 1) if a and b else None
            if filled_at is None:
                status = "stopped_pre_entry" if stopped_at is None and any(
                    (float(c["high"]) >= stop) if direction == "bearish" else (float(c["low"]) <= stop)
                    for c in fwd
                ) else "expired"
                if status == "stopped_pre_entry":
                    reason = ("Price ran away before the entry zone was touched — the stop level "
                              "was breached first, so the plan was never tradeable. The entry zone "
                              "was too far from the current market when the plan was made.")
                else:
                    reason = ("Entry zone was never touched within the 5-day horizon — the market "
                              f"moved without revisiting the level (final price {float(fwd[-1]['close']):.0f}).")
            elif stopped_at is not None and t1_at is None:
                status = "stopped"
                hours_held = hours(filled_at, stopped_at)
                reason = (f"Stop hit {hours_held}h after entry — the bounce invalidated the call "
                          f"before any target was reached (max favorable move ${fav:.0f}/oz).")
            elif t1_at is not None and stopped_at is not None and t2_at is None and stopped_at > t1_at:
                status = "hit_t1"
                reason = (f"T1 hit {hours(filled_at, t1_at)}h after entry; the remaining half was "
                          f"stopped at breakeven {hours(t1_at, stopped_at)}h later — plan rules capped "
                          f"the loss on the runner at zero.")
            elif t2_at is not None:
                status = "hit_t2"
                reason = (f"Full plan achieved: T1 {hours(filled_at, t1_at)}h after entry, T2 "
                          f"{hours(t1_at, t2_at)}h later — the trend continued as predicted "
                          f"(total move ${fav:.0f}/oz from entry).")
            elif t1_at is not None:
                status = "hit_t1"
                reason = (f"T1 hit {hours(filled_at, t1_at)}h after entry; T2 was not reached "
                          f"within the 5-day horizon (max favorable ${fav:.0f}/oz).")
            else:
                status = "expired"
                reason = (f"Entry filled but neither stop nor targets were reached within the "
                          f"5-day horizon (max favorable ${fav:.0f}/oz) — the call drifted without "
                          f"following through.")

            conn.execute(
                """
                UPDATE prediction_audit
                SET status = %s, entry_filled_at = %s, t1_hit_at = %s, t2_hit_at = %s,
                    stopped_at = %s, max_favorable = %s, graded_at = %s, reason = %s
                WHERE id = %s
                """,
                (status, filled_at, t1_at, t2_at, stopped_at, fav, now, reason, p["id"]),
            )
            graded += 1

    # overlap pass: a plan that was never filled but had a LATER plan issued
    # was superseded, not expired — otherwise regeneration drowns the signal
    with get_pool().connection() as conn:
        conn.execute(
            """
            UPDATE prediction_audit pa
            SET status = 'superseded', graded_at = now(),
                reason = 'Superseded: a newer plan was issued before this entry zone was ever touched.'
            WHERE pa.symbol = %s AND pa.status = 'expired' AND pa.entry_filled_at IS NULL
              AND EXISTS (SELECT 1 FROM prediction_audit b
                          WHERE b.symbol = pa.symbol AND b.created_at > pa.created_at)
            """,
            (symbol,),
        )
    return graded


def audit_summary(symbol: str = "XAUUSD") -> dict:
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT status, count(*) n FROM prediction_audit WHERE symbol = %s GROUP BY 1",
            (symbol.upper(),),
        ).fetchall()
    counts = {r["status"]: r["n"] for r in rows}
    decided = sum(counts.get(k, 0) for k in ("hit_t1", "hit_t2", "stopped", "expired"))
    t1_rate = (counts.get("hit_t1", 0) + counts.get("hit_t2", 0)) / decided if decided else None
    return {
        "total": sum(counts.values()),
        "pending": counts.get("pending", 0),
        "decided": decided,
        "superseded": counts.get("superseded", 0),
        "hit_t1": counts.get("hit_t1", 0),
        "hit_t2": counts.get("hit_t2", 0),
        "stopped": counts.get("stopped", 0),
        "superseded": counts.get("superseded", 0),
        "expired": counts.get("expired", 0),
        "t1_hit_rate": round(t1_rate, 2) if t1_rate is not None else None,
    }


def backfill_from_history(symbol: str = "XAUUSD") -> int:
    """Snapshot every historical verdict that carried a plan but was never audited."""
    symbol = symbol.upper()
    n = 0
    with get_pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT v.id, v.symbol, v.direction, v.plan
            FROM daily_verdicts v
            LEFT JOIN prediction_audit pa ON pa.verdict_id = v.id
            WHERE v.symbol = %s AND pa.id IS NULL AND v.plan ? 'stop' AND v.plan ? 't1'
            ORDER BY v.as_of
            """,
            (symbol,),
        ).fetchall()
    for r in rows:
        plan = r["plan"]
        if not isinstance(plan, dict) or plan.get("stop") is None or plan.get("t1") is None:
            continue
        with get_pool().connection() as conn:
            conn.execute(
                """
                INSERT INTO prediction_audit
                    (verdict_id, symbol, direction, mode, entry_low, entry_high,
                     stop, t1, t2, horizon_days, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        COALESCE((SELECT as_of FROM daily_verdicts WHERE id = %s), now()))
                """,
                (
                    r["id"], r["symbol"], r["direction"],
                    (plan.get("mode") or "pullback"),
                    plan.get("entry_low"), plan.get("entry_high"),
                    plan.get("stop"), plan.get("t1"), plan.get("t2"), HORIZON_DAYS,
                    r["id"],
                ),
            )
        n += 1
    return n
