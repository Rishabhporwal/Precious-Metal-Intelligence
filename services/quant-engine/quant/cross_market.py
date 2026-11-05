"""Cross-market intelligence (enhancement spec §6): gold vs USD, yields, real yields.

Deterministic daily-granularity analysis from stored FRED macro observations
and gold daily candles. With the free data plan these series are daily — the
output says so. Correlation is context, never proof of causation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db import get_pool

FACTORS = [
    ("DTWEXBGS", "Broad USD", "inverse"),   # gold typically falls when USD rises
    ("DGS10", "10Y yield", "inverse"),      # higher nominal yields pressure gold
    ("DFII10", "10Y real yield", "inverse"),
]


def _pct_returns(values: list[float]) -> list[float]:
    return [(b - a) / a * 100 for a, b in zip(values, values[1:], strict=False)]


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = min(len(xs), len(ys))
    if n < 10:
        return None
    xs, ys = xs[-n:], ys[-n:]
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=False))
    vx = sum((x - mx) ** 2 for x in xs) ** 0.5
    vy = sum((y - my) ** 2 for y in ys) ** 0.5
    if vx == 0 or vy == 0:
        return None
    return cov / (vx * vy)


def cross_market_summary(symbol: str = "XAUUSD", days: int = 60) -> dict:
    """Per-factor: recent gold direction, factor direction, 30d correlation,
    and whether the factor SUPPORTS or CONTRADICTS the recent gold move."""
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=days)
    with get_pool().connection() as conn:
        inst = conn.execute(
            "SELECT id FROM instruments WHERE symbol = %s", (symbol.upper(),)
        ).fetchone()
        if inst is None:
            return {"error": f"unknown instrument {symbol}"}
        gold = conn.execute(
            """
            SELECT market_ts, close FROM market_candles
            WHERE instrument_id = %s AND interval = '1day' AND market_ts >= %s
            ORDER BY market_ts
            """,
            (inst["id"], cutoff),
        ).fetchall()
        factors_out: list[dict] = []
        for series_id, label, expected in FACTORS:
            obs = conn.execute(
                """
                SELECT as_of_date, value FROM macro_observations
                WHERE series_id = %s AND as_of_date >= %s ORDER BY as_of_date
                """,
                (series_id, cutoff.date()),
            ).fetchall()
            if len(gold) < 12 or len(obs) < 10:
                factors_out.append({
                    "series_id": series_id, "label": label, "status": "insufficient_data",
                })
                continue
            gold_dates = {r["market_ts"].date(): float(r["close"]) for r in gold}
            paired_gold, paired_factor = [], []
            for o in obs:
                d = o["as_of_date"]
                if o["value"] is None:
                    continue  # revised/missing observations — skip, never invent
                if d in gold_dates:
                    paired_gold.append(gold_dates[d])
                    paired_factor.append(float(o["value"]))
            if len(paired_gold) < 10:
                factors_out.append({"series_id": series_id, "label": label, "status": "insufficient_data"})
                continue
            g_ret = _pct_returns(paired_gold)
            f_ret = _pct_returns(paired_factor) if expected == "inverse" else paired_factor[1:]
            corr = _pearson(g_ret, f_ret)
            gold_dir = paired_gold[-1] - paired_gold[-6] if len(paired_gold) >= 6 else 0
            factor_dir = paired_factor[-1] - paired_factor[-6] if len(paired_factor) >= 6 else 0
            # expected inverse: factor up while gold up = CONTRADICTS gold's move
            same_direction = (gold_dir > 0 and factor_dir > 0) or (gold_dir < 0 and factor_dir < 0)
            if expected == "inverse":
                relation = "contradicts" if same_direction and abs(gold_dir) > 0 else (
                    "supports" if not same_direction and abs(gold_dir) > 0 else "neutral")
            else:
                relation = "supports" if same_direction and abs(gold_dir) > 0 else (
                    "contradicts" if not same_direction and abs(gold_dir) > 0 else "neutral")
            corr_str = f"{corr:.2f}" if corr is not None else "—"
            factors_out.append({
                "series_id": series_id,
                "label": label,
                "status": "ok",
                "gold_5d_change": round(gold_dir, 2),
                "factor_5d_change": round(factor_dir, 2),
                "correlation_60d": corr_str,
                "relation_to_gold_move": relation,
                "granularity": "daily (FRED) — intraday cross-market needs a paid data plan",
            })

    gold_last = float(gold[-1]["close"]) if gold else None
    gold_first = float(gold[0]["close"]) if gold else None
    recent_move = ((gold_last - gold_first) / gold_first * 100) if gold_last and gold_first else None
    return {
        "symbol": symbol.upper(),
        "as_of": now.isoformat(),
        "gold_change_pct_window": round(recent_move, 2) if recent_move is not None else None,
        "window_days": days,
        "factors": factors_out,
        "note": "correlation is context, not causation; daily granularity on the free data plan",
    }
