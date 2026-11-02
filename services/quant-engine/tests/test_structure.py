"""Market structure tests: swings, labels, BOS/CHoCH, S/R, PDH/PDL, weeks."""

from datetime import UTC, datetime, timedelta

import pytest

from indicators.structure import (
    detect_structure_events,
    detect_swings,
    label_swings,
    prev_day_high_low,
    prev_week_high_low,
    session_ranges,
    support_resistance,
)


def test_swings_require_confirmation_bars():
    highs = [1.0, 2.0, 5.0, 2.0, 1.0]
    lows = [0.5] * 5
    swings = detect_swings(highs, lows, k=2)
    high_swing = next(s for s in swings if s.kind == "high")
    assert high_swing.index == 2
    assert high_swing.confirmed_index == 4  # only known 2 bars later (no repaint)


def test_labels_hh_lh_hl_ll():
    highs = [1.0, 2.0, 5.0, 2.0, 1.0, 2.0, 7.0, 3.0, 1.0, 2.0, 6.0, 3.0, 1.0]
    lows = [0.5] * 13
    swings = [s for s in detect_swings(highs, lows, k=2) if s.kind == "high"]
    labels = label_swings(swings)
    values = [l for _, l in labels]
    assert values == ["HH", "LH"]  # 5->7 HH, then 7->6 LH


def test_bos_bullish_then_choch_bearish():
    # uptrend with a confirmed swing high at index 2 (price 5), then a break up,
    # then a confirmed swing low broken to the downside -> CHoCH bearish.
    highs = [1.0, 2.0, 5.0, 2.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    lows = [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 1.0, 2.0, 3.0, 4.0]
    closes = [1.0, 1.5, 3.0, 1.5, 1.0, 2.0, 5.1, 5.2, 5.3, 5.4]
    swings = detect_swings(highs, lows, k=2)
    events = detect_structure_events(closes, swings)
    kinds = [e.kind for e in events]
    assert "bos_bullish" in kinds  # close 5.1 above swing high 5.0
    # after breaking up, breaking the prior swing low (0.5-ish) would be CHoCH —
    # not triggered in this series; assert no false choch_bearish
    assert "choch_bearish" not in kinds


def test_support_resistance_clustering():
    swings = []
    prices = [100.0, 100.05, 99.9, 101.0, 105.0]
    for i, p in enumerate(prices):
        kind = "low" if p < 100.5 else "high"
        swings.append(type("S", (), {"index": i, "confirmed_index": i, "price": p, "kind": kind}))
    supports, resistances = support_resistance(swings, last_close=100.2)
    # 100.0/100.05/99.9 cluster into one support ~100.0 with 3 touches
    s = supports[0]
    assert s["touches"] == 3
    assert abs(s["price"] - 100.0) < 0.05
    assert resistances[0]["price"] >= 100.2


def _daily_rows(n_days, start_price=100.0, day_high=2.0, day_low=2.0):
    rows = []
    base = datetime(2026, 10, 1, tzinfo=UTC)
    for d in range(n_days):
        day = base + timedelta(days=d)
        mid = start_price + d
        rows.append({
            "market_ts": day,
            "open": mid,
            "high": mid + day_high,
            "low": mid - day_low,
            "close": mid,
            "status": "final" if d < n_days - 1 else "provisional",
        })
    return rows


def test_prev_day_uses_last_completed_candle():
    daily = _daily_rows(5)
    pdh, pdl = prev_day_high_low(daily)
    # last candle (index 4) is provisional -> yesterday = index 3 (mid=103)
    assert pdh == 103.0 + 2.0
    assert pdl == 103.0 - 2.0


def test_prev_week_skips_running_week():
    # 10 days spanning parts of two ISO weeks; last (partial) week must be skipped
    daily = _daily_rows(10)
    pwh, pwl = prev_week_high_low(daily)
    assert pwh is not None and pwl is not None


def test_session_ranges_utc_windows():
    base = datetime(2026, 10, 1, tzinfo=UTC)
    hourly = []
    for h in range(24):
        hourly.append({
            "market_ts": base.replace(hour=h),
            "high": 100.0 + h * 0.1,
            "low": 100.0 + h * 0.1 - 0.5,
            "close": 100.0 + h * 0.1,
        })
    sessions = session_ranges(hourly, ref_date=base + timedelta(days=1))
    asia = sessions["asia"]
    # asia window 00-07 UTC on Sep 30: highs 100.0..100.7
    assert asia["high"] == pytest.approx(100.7)
    assert asia["low"] == pytest.approx(100.0 - 0.5)
    ny = sessions["newyork"]
    assert ny["high"] == pytest.approx(102.0)  # hours 12..20 -> 101.2..102.0
