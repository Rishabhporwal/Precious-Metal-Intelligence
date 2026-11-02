"""Quant stats tests: correlation math, as-of join, regime, scenario stats."""

from datetime import date, datetime

import pytest  # noqa: F401

from quant import correlations as corr
from quant import regimes as reg
from quant import scenarios as scn


def test_pearson_perfect_and_inverse():
    assert corr.pearson([1, 2, 3, 4], [2, 4, 6, 8]) == pytest.approx(1.0)
    assert corr.pearson([1, 2, 3, 4], [8, 6, 4, 2]) == pytest.approx(-1.0)
    assert corr.pearson([1, 2], [1, 2]) is None  # too few points


def test_asof_join_staleness():
    series = {date(2026, 1, 1): 10.0, date(2026, 1, 5): 12.0}
    dates = [
        datetime(2026, 1, 1), datetime(2026, 1, 3), datetime(2026, 1, 5), datetime(2026, 1, 20),
    ]
    out = corr.asof_join(dates, series, max_stale_days=7)
    assert out == [10.0, 10.0, 12.0, None]  # Jan 20 is >7 days stale -> None


def test_returns_missing_preserved():
    out = corr.returns([100.0, None, 110.0])
    assert out == [None, None, None] or out[2] is None
    out2 = corr.returns([100.0, 110.0])
    assert out2[0] is None
    assert out2[1] == pytest.approx(10.0)


def test_regime_trending_up_low_vol():
    closes = [100.0 + i * 0.2 for i in range(300)]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    r = reg.regime_report(closes, highs, lows)
    assert r["trend"]["trend"] == "up"
    assert r["vol"]["vol_regime"] in ("low", "normal")


def test_scenario_buckets_and_stats():
    # build 600 days: alternating mild zigzag with a final oversold low
    closes = []
    base = 100.0
    for i in range(600):
        base += (-0.4 if (i // 10) % 2 == 0 else 0.4)
        closes.append(base)
    rep = scn.scenario_report(closes)
    assert rep["history_years"] > 2
    assert "current_bucket" in rep
    # forward stats include n and median
    for horizon, s in rep["bucket_history"].items():
        assert s["n"] > 0
        assert "median_pct" in s and "up_rate" in s


def test_scenario_no_lookahead_buckets():
    """A bar's bucket must be computable from data up to that bar only."""
    closes = [100.0 + (i % 7) * 0.3 for i in range(300)]
    from indicators import historical_volatility as hv_fn
    from indicators import rsi as rsi_fn
    from indicators import volatility_percentile as vp_fn
    r = rsi_fn(closes)
    hv = hv_fn(closes, 20)
    vp = vp_fn(hv, 252)
    full_r = rsi_fn(closes + [closes[-1]])
    full_hv = hv_fn(closes + [closes[-1]], 20)
    full_vp = vp_fn(full_hv, 252)
    for i in range(len(closes)):
        assert r[i] == full_r[i]
        assert hv[i] == full_hv[i]
        assert vp[i] == full_vp[i]
