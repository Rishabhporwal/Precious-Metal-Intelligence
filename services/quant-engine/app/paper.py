"""Paper trading engine: virtual accounts, fills, SL/TP monitoring, P&L.

Simulated execution only — explicitly labeled; no live broker integration.
Fills assume: market entry at latest stored quote; stop fills at the worse of
stop price / current quote (pessimistic, honest); target fills at the target.
"""

from __future__ import annotations

from app.db import get_pool
from app.marketdata import store


def _num(v) -> float | None:
    return float(v) if v is not None else None


def ensure_default_account(risk_pct: float = 1.0) -> int:
    with get_pool().connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO paper_accounts (name, initial_balance, risk_pct_per_trade)
            VALUES ('default', 1000.0, %s)
            ON CONFLICT (name) DO NOTHING
            RETURNING id
            """,
            (risk_pct,),
        )
        row = cur.fetchone()
        if row:
            return int(row["id"])
        cur = conn.execute("SELECT id FROM paper_accounts WHERE name = 'default'")
        return int(cur.fetchone()["id"])


def _latest_price(conn, instrument_id: int) -> float | None:
    q = conn.execute(
        "SELECT price FROM market_quotes WHERE instrument_id = %s ORDER BY market_ts DESC LIMIT 1",
        (instrument_id,),
    ).fetchone()
    return _num(q["price"]) if q else None


def open_trade(
    account_id: int,
    symbol: str,
    direction: str,
    size: float,
    stop: float | None,
    target: float | None,
    setup_id: int | None = None,
) -> dict:
    """Open a paper position at the latest quote (market order)."""
    with get_pool().connection() as conn:
        inst = store.get_instrument_by_symbol(conn, symbol)
        if inst is None:
            raise ValueError(f"unknown instrument {symbol}")
        price = _latest_price(conn, inst["id"])
        if price is None:
            raise ValueError("no fresh quote available for paper fill")
        cur = conn.execute(
            """
            INSERT INTO paper_trades
                (account_id, instrument_id, direction, size, entry_price, stop, target, setup_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (account_id, inst["id"], direction, size, price, stop, target, setup_id),
        )
        trade = cur.fetchone()
        conn.execute(
            """
            INSERT INTO paper_trade_fills (trade_id, side, qty, price)
            VALUES (%s, %s, %s, %s)
            """,
            (trade["id"], "buy" if direction == "long" else "sell", size, price),
        )
    return _trade_view(trade, current_price=price)


def close_trade(trade_id: int, reason: str = "manual") -> dict:
    """Close at the latest quote (or stop price if reason == stop — pessimistic)."""
    with get_pool().connection() as conn:
        t = conn.execute("SELECT * FROM paper_trades WHERE id = %s", (trade_id,)).fetchone()
        if t is None:
            raise ValueError("trade not found")
        if t["status"] == "closed":
            return _trade_view(t)
        price = _latest_price(conn, t["instrument_id"])
        if price is None:
            raise ValueError("no fresh quote to close against")
        if reason == "stop" and t["stop"] is not None:
            stop = _num(t["stop"])
            if t["direction"] == "long":
                price = min(price, stop)
            else:
                price = max(price, stop)
        conn.execute(
            """
            UPDATE paper_trades
            SET exit_price = %s, exit_time = now(), exit_reason = %s, status = 'closed'
            WHERE id = %s
            """,
            (price, reason, trade_id),
        )
        conn.execute(
            """
            INSERT INTO paper_trade_fills (trade_id, side, qty, price)
            VALUES (%s, %s, %s, %s)
            """,
            (trade_id, "sell" if t["direction"] == "long" else "buy", t["size"], price),
        )
        # link outcome to setup if this came from one
        if t["setup_id"] is not None:
            entry = _num(t["entry_price"])
            stop = _num(t["stop"])
            exit = float(price)
            direction = t["direction"]
            if stop and entry and stop != entry:
                sign = 1 if direction == "long" else -1
                risk = (entry - stop) * sign
                r_multiple = (exit - entry) * sign / risk if risk > 0 else None
                outcome = "win" if r_multiple and r_multiple > 0 else "loss"
                conn.execute(
                    """
                    INSERT INTO trade_outcomes (setup_id, paper_trade_id, outcome, r_multiple)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (t["setup_id"], trade_id, outcome, r_multiple),
                )
        refreshed = conn.execute("SELECT * FROM paper_trades WHERE id = %s", (trade_id,)).fetchone()
    return _trade_view(refreshed, current_price=price)


def monitor_open_trades() -> dict:
    """Check every open trade against the latest quote: stop/target exits."""
    closed = {"stops": 0, "targets": 0}
    with get_pool().connection() as conn:
        open_trades = conn.execute("SELECT * FROM paper_trades WHERE status = 'open'").fetchall()
    for t in open_trades:
        with get_pool().connection() as conn:
            price = _latest_price(conn, t["instrument_id"])
        if price is None:
            continue
        stop = _num(t["stop"])
        target = _num(t["target"])
        if t["direction"] == "long":
            if stop is not None and price <= stop:
                close_trade(int(t["id"]), reason="stop")
                closed["stops"] += 1
            elif target is not None and price >= target:
                close_trade(int(t["id"]), reason="target")
                closed["targets"] += 1
        else:
            if stop is not None and price >= stop:
                close_trade(int(t["id"]), reason="stop")
                closed["stops"] += 1
            elif target is not None and price <= target:
                close_trade(int(t["id"]), reason="target")
                closed["targets"] += 1
    return closed


def account_summary(account_id: int) -> dict:
    with get_pool().connection() as conn:
        acc = conn.execute("SELECT * FROM paper_accounts WHERE id = %s", (account_id,)).fetchone()
        if acc is None:
            raise ValueError("account not found")
        open_trades = conn.execute(
            "SELECT * FROM paper_trades WHERE account_id = %s AND status = 'open'",
            (account_id,),
        ).fetchall()
        closed_trades = conn.execute(
            """
            SELECT * FROM paper_trades WHERE account_id = %s AND status = 'closed'
            ORDER BY exit_time DESC
            """,
            (account_id,),
        ).fetchall()

    unrealized = 0.0
    positions = []
    for t in open_trades:
        with get_pool().connection() as conn:
            price = _latest_price(conn, t["instrument_id"]) or _num(t["entry_price"])
        pnl = (price - _num(t["entry_price"])) * _num(t["size"]) * (1 if t["direction"] == "long" else -1)
        unrealized += pnl
        positions.append(_trade_view(t, current_price=price))

    realized = sum(
        (_num(t["exit_price"]) - _num(t["entry_price"])) * _num(t["size"]) * (1 if t["direction"] == "long" else -1)
        for t in closed_trades
        if _num(t["exit_price"]) is not None
    )
    wins = [t for t in closed_trades if (_num(t["exit_price"]) - _num(t["entry_price"])) * (1 if t["direction"] == "long" else -1) > 0]
    equity = float(acc["initial_balance"]) + realized + unrealized
    return {
        "account_id": account_id,
        "name": acc["name"],
        "initial_balance": float(acc["initial_balance"]),
        "risk_pct_per_trade": float(acc["risk_pct_per_trade"]),
        "equity": round(equity, 2),
        "realized_pnl": round(realized, 2),
        "unrealized_pnl": round(unrealized, 2),
        "open_positions": positions,
        "closed_trades": [_trade_view(t) for t in closed_trades[:20]],
        "stats": {
            "closed_count": len(closed_trades),
            "win_count": len(wins),
            "win_rate": round(len(wins) / len(closed_trades), 3) if closed_trades else None,
        },
        "note": "SIMULATED paper trading — no live orders are ever placed",
    }


def _trade_view(t, current_price: float | None = None) -> dict:
    entry = _num(t["entry_price"])
    pnl = None
    if current_price is not None:
        pnl = round(
            (current_price - entry) * _num(t["size"]) * (1 if t["direction"] == "long" else -1), 2
        )
    elif t["exit_price"] is not None:
        pnl = round(
            (_num(t["exit_price"]) - entry) * _num(t["size"]) * (1 if t["direction"] == "long" else -1), 2
        )
    return {
        "id": int(t["id"]),
        "direction": t["direction"],
        "size": _num(t["size"]),
        "entry_price": entry,
        "entry_time": t["entry_time"].isoformat() if t["entry_time"] else None,
        "stop": _num(t["stop"]),
        "target": _num(t["target"]),
        "exit_price": _num(t["exit_price"]),
        "exit_reason": t["exit_reason"],
        "status": t["status"],
        "setup_id": _num(t["setup_id"]) if t["setup_id"] else None,
        "current_price": current_price,
        "unrealized_or_realized_pnl": pnl,
    }
