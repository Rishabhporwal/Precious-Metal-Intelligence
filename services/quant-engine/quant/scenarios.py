"""Historical scenario comparison — empirical forward-return statistics.

Method (deterministic, reproducible):
- bucket each historical bar by its RSI(14) and volatility-percentile state
  (computed only from data up to that bar — no lookahead)
- for the bar's bucket, collect forward returns over 5/10/20 trading days
- report median / mean / up-rate / sample size for the CURRENT bucket

These are EMPIRICAL FREQUENCIES over the stored history, clearly labeled with
their sample size. They are not predictions and carry no confidence claims
beyond the observed sample.
"""

from __future__ import annotations

from statistics import mean, median

from indicators import historical_volatility, rsi, volatility_percentile

FORWARD_HORIZONS = (5, 10, 20)


def _bucket(rsi_v: float | None, vp: float | None) -> str:
    rsi_b = "unknown" if rsi_v is None else "oversold" if rsi_v < 30 else "overbought" if rsi_v > 70 else "neutral"
    vol_b = "unknown" if vp is None else "low-vol" if vp < 25 else "high-vol" if vp > 75 else "mid-vol"
    return f"{rsi_b}/{vol_b}"


def _forward_stats(closes: list[float], indices: list[int], horizon: int) -> dict | None:
    vals = []
    for i in indices:
        if i + horizon < len(closes):
            entry = closes[i]
            vals.append((closes[i + horizon] / entry - 1.0) * 100.0)
    if not vals:
        return None
    return {
        "n": len(vals),
        "median_pct": round(median(vals), 3),
        "mean_pct": round(mean(vals), 3),
        "up_rate": round(sum(1 for v in vals if v > 0) / len(vals), 3),
    }


def scenario_report(closes: list[float]) -> dict:
    n = len(closes)
    if n < 260:
        return {"error": "need >= 260 daily candles for scenario statistics"}
    r = rsi(closes, 14)
    hv = historical_volatility(closes, 20)
    vp = volatility_percentile(hv, lookback=252)

    buckets: dict[str, list[int]] = {}
    for i in range(n):
        # rsi/vp at bar i are trailing by construction (indicator warm-up skipped)
        b = _bucket(r[i], vp[i])
        if b != "unknown/unknown":
            buckets.setdefault(b, []).append(i)

    current_bucket = _bucket(r[-1], vp[-1])

    stats = {}
    for horizon in FORWARD_HORIZONS:
        s = _forward_stats(closes, buckets.get(current_bucket, []), horizon)
        if s:
            stats[f"{horizon}d"] = s

    all_hist = _forward_stats(closes, list(range(n - max(FORWARD_HORIZONS))), max(FORWARD_HORIZONS))

    return {
        "current_bucket": current_bucket,
        "current_rsi": round(r[-1], 1) if r[-1] is not None else None,
        "current_vol_percentile": round(vp[-1], 1) if vp[-1] is not None else None,
        "bucket_history": stats,
        "baseline": {f"{max(FORWARD_HORIZONS)}d": all_hist} if all_hist else {},
        "bucket_counts": {k: len(v) for k, v in sorted(buckets.items())},
        "history_years": round(n / 252, 1),
        "note": (
            "Empirical frequencies over stored history for bars in the same regime bucket. "
            "Sample sizes shown; small n means weak evidence. Not predictions."
        ),
    }
