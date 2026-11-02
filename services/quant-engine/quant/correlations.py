"""Cross-market correlation engine (deterministic, as-of joined, no lookahead)."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta


def _to_date(d) -> date:
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    return date.fromisoformat(str(d)[:10])


def pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    vx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    vy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if vx == 0 or vy == 0:
        return None
    return cov / (vx * vy)


def build_series(series_rows: list[dict]) -> dict[date, float]:
    """macro_observations rows -> {date: value} (latest vintage per date wins)."""
    out: dict[date, float] = {}
    for r in sorted(series_rows, key=lambda r: r["fetched_at"]):
        d = _to_date(r["as_of_date"])
        v = r["value"]
        if v is not None:
            out[d] = float(v)
    return out


def asof_join(
    candle_dates: list[datetime | date],
    series: dict[date, float],
    max_stale_days: int = 7,
) -> list[float | None]:
    """For each candle date, the most recent series value on/before it (else None)."""
    sorted_dates = sorted(series)
    out: list[float | None] = []
    j = -1
    for raw in candle_dates:
        d = _to_date(raw)
        while j + 1 < len(sorted_dates) and sorted_dates[j + 1] <= d:
            j += 1
        if j >= 0 and d - sorted_dates[j] <= timedelta(days=max_stale_days):
            out.append(series[sorted_dates[j]])
        else:
            out.append(None)
    return out


def returns(values: list[float | None]) -> list[float | None]:
    """Daily percent returns; None preserved where inputs are missing."""
    out: list[float | None] = [None]
    for i in range(1, len(values)):
        a, b = values[i - 1], values[i]
        if a is None or b is None or a == 0:
            out.append(None)
        else:
            out.append((b / a - 1.0) * 100.0)
    return out


def rolling_correlation(
    gold_returns: list[float | None],
    other_returns: list[float | None],
    window: int = 30,
    min_pairs_frac: float = 0.6,
) -> list[float | None]:
    """Rolling Pearson over PAIRED returns (both defined at the same index)."""
    n = len(gold_returns)
    out: list[float | None] = [None] * n
    for i in range(window, n):
        pairs = [
            (gold_returns[j], other_returns[j])
            for j in range(i - window, i)
            if gold_returns[j] is not None and other_returns[j] is not None
        ]
        if len(pairs) < window * min_pairs_frac:  # tolerate missing macro days
            continue
        r = pearson([p[0] for p in pairs], [p[1] for p in pairs])
        out[i] = r
    return out


def correlation_summary(
    candle_dates: list[datetime],
    gold_closes: list[float],
    macro: dict[str, dict[date, float]],
    window: int = 30,
) -> list[dict]:
    """Correlation of gold daily returns vs each macro series' returns.

    Reports: current rolling correlation, its 30d change, and full-sample corr.
    """
    dates = [_to_date(d) for d in candle_dates]
    gold_ret = returns(gold_closes)
    out = []
    for series_id, series in macro.items():
        joined = asof_join(dates, series)
        other_ret = returns(joined)
        roll = rolling_correlation(gold_ret, other_ret, window)
        defined = [v for v in roll if v is not None]
        if not defined:
            continue
        current = defined[-1]
        prev = defined[-31] if len(defined) >= 31 else None
        paired = [(g, o) for g, o in zip(gold_ret, other_ret, strict=True) if g is not None and o is not None]
        full = pearson([p[0] for p in paired], [p[1] for p in paired]) if paired else None
        # last macro date for freshness reporting
        last_series_date = max(series) if series else None
        out.append({
            "series_id": series_id,
            "rolling_30d": round(current, 3) if current is not None else None,
            "rolling_30d_prev": round(prev, 3) if prev is not None else None,
            "full_sample": round(full, 3) if full is not None else None,
            "last_macro_date": last_series_date.isoformat() if last_series_date else None,
        })
    return out
