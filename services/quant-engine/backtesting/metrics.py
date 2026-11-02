"""Backtesting metrics (from simulated trade records)."""

from __future__ import annotations

import math
from datetime import datetime
from statistics import mean, median


def compute_metrics(
    trades: list[dict],
    initial_equity: float = 1000.0,
    risk_per_trade: float = 10.0,
) -> dict:
    """trades: dicts with r_multiple (float|None), pnl, entry_time, exit_time, direction."""
    closed = [t for t in trades if t.get("exit_price") is not None]
    if not closed:
        return {"closed_trades": 0, "note": "no closed trades in this run"}

    rs = [t["r_multiple"] for t in closed if t.get("r_multiple") is not None]
    pnls = [t["pnl"] for t in closed if t.get("pnl") is not None]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]

    gross_win = sum(pnl for pnl in pnls if pnl > 0)
    gross_loss = abs(sum(pnl for pnl in pnls if pnl < 0))

    # equity curve on fixed risk-per-trade
    equity = initial_equity
    curve = [equity]
    for r in rs:
        equity += r * risk_per_trade
        curve.append(equity)
    peak = curve[0]
    max_dd = 0.0
    for v in curve:
        peak = max(peak, v)
        max_dd = max(max_dd, (peak - v) / peak)

    def sharpe(values: list[float]) -> float | None:
        if len(values) < 2:
            return None
        m = mean(values)
        sd = math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))
        return round(m / sd, 3) if sd > 0 else None

    def sortino(values: list[float]) -> float | None:
        if len(values) < 2:
            return None
        m = mean(values)
        downside = math.sqrt(sum(v * v for v in values if v < 0) / len(values))
        return round(m / downside, 3) if downside > 0 else None

    hold_hours = []
    for t in closed:
        if t.get("entry_time") and t.get("exit_time"):
            try:
                e = t["entry_time"] if isinstance(t["entry_time"], datetime) else datetime.fromisoformat(str(t["entry_time"]))
                x = t["exit_time"] if isinstance(t["exit_time"], datetime) else datetime.fromisoformat(str(t["exit_time"]))
                hold_hours.append((x - e).total_seconds() / 3600)
            except (TypeError, ValueError):
                pass

    by_session: dict[str, list[float]] = {}
    for t in closed:
        if t.get("entry_time"):
            dt = t["entry_time"] if isinstance(t["entry_time"], datetime) else datetime.fromisoformat(str(t["entry_time"]))
            sess = "asia" if dt.hour < 7 else "london" if dt.hour < 12 else "newyork" if dt.hour < 21 else "late"
            by_session.setdefault(sess, []).append(t.get("r_multiple") or 0.0)

    return {
        "closed_trades": len(closed),
        "win_rate": round(len(wins) / len(rs), 3) if rs else None,
        "profit_factor": round(gross_win / gross_loss, 3) if gross_loss > 0 else (None if gross_win == 0 else round(gross_win, 3)),
        "expectancy_r": round(mean(rs), 3) if rs else None,
        "median_r": round(median(rs), 3) if rs else None,
        "avg_win_r": round(mean(wins), 3) if wins else None,
        "avg_loss_r": round(mean(losses), 3) if losses else None,
        "total_pnl": round(sum(pnls), 2),
        "total_costs": round(sum(t.get("costs", 0) for t in closed), 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "sharpe_per_trade": sharpe(rs),
        "sortino_per_trade": sortino(rs),
        "avg_hold_hours": round(mean(hold_hours), 1) if hold_hours else None,
        "by_session": {
            k: {"n": len(v), "expectancy_r": round(mean(v), 3), "win_rate": round(sum(1 for x in v if x > 0) / len(v), 3)}
            for k, v in by_session.items()
        },
        "note": "per-trade Sharpe/Sortino (not annualized); R multiples net of costs",
    }
