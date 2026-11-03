"""P1 strategy tests: deterministic synthetic fixtures per new strategy."""

from datetime import UTC, datetime, timedelta

from indicators.structure import full_structure_report
from strategies.base import build_context
from strategies.ict_p1 import (
    AmdPowerOfThreeStrategy,
    IctSilverBulletStrategy,
    JudasSwingStrategy,
    LiquidityVoidStrategy,
    SessionRangeBreakoutStrategy,
)
from strategies.quant_strategies import (
    HiddenDivergenceStrategy,
    TrendExhaustionStrategy,
    VolatilityRegimeStrategy,
    WyckoffSosSowStrategy,
)


def _ctx(closes, highs=None, lows=None):
    rows = []
    t0 = datetime(2026, 6, 1, tzinfo=UTC)  # a Monday, so hour 0 = daily boundary
    n = len(closes)
    for i, c in enumerate(closes):
        rows.append({
            "market_ts": t0 + timedelta(hours=i),
            "open": closes[i - 1] if i else c,
            "high": (highs[i] if highs else c + 1.0),
            "low": (lows[i] if lows else c - 1.0),
            "close": c, "status": "final",
        })
    daily, hourly = rows, rows
    rep = full_structure_report(
        [r["high"] for r in rows], [r["low"] for r in rows], [r["close"] for r in rows],
        daily, hourly,
    )
    return build_context("XAUUSD", "1h", rows, daily, hourly, structure=rep) if False else build_context(
        "XAUUSD", "1h", rows, daily, hourly,
    )


def test_silver_bullet_window_gating():
    # FVG only counts when its third candle sits inside 15:00-16:00 UTC
    closes = [100.0] * 75
    # place a bullish FVG ending at hour 15 (the 16th candle of the day)
    day_start = 0
    i = day_start + 15  # hour 15
    closes[i - 2] = 100.0   # candle1 high base
    closes[i - 1] = 110.0   # huge middle candle
    closes[i] = 112.0       # third candle
    rows = []
    t0 = datetime(2026, 6, 1, tzinfo=UTC)
    for k, c in enumerate(closes):
        rows.append({
            "market_ts": t0 + timedelta(hours=k),
            "open": closes[k - 1] if k else c,
            "high": max(c, closes[k - 1] if k else c) + 0.5,
            "low": min(c, closes[k - 1] if k else c) - 0.5,
            "close": c, "status": "final",
        })
    ctx = build_context("XAUUSD", "1h", rows, rows, rows)
    dets = IctSilverBulletStrategy().detect(ctx)
    assert dets, "expected a silver-bullet FVG at hour 15"
    assert all(15 <= d.anchor_time.hour < 16 for d in dets)


def test_liquidity_void_direction_and_bounds():
    # one big bullish displacement candle leaves a void; verdict is bearish (rebalance)
    closes = [100.0] * 90
    i = 80
    closes[i] = 108.0  # +8 body on ~1 ATR context
    rows = []
    t0 = datetime(2026, 6, 1, tzinfo=UTC)
    for k, c in enumerate(closes):
        rows.append({
            "market_ts": t0 + timedelta(hours=k),
            "open": closes[k - 1] if k else c,
            "high": max(c, closes[k - 1] if k else c) + 0.3,
            "low": min(c, closes[k - 1] if k else c) - 0.3,
            "close": c, "status": "final",
        })
    ctx = build_context("XAUUSD", "1h", rows, rows, rows)
    dets = LiquidityVoidStrategy().detect(ctx)
    assert dets, "expected liquidity void detection"
    assert any(d.direction == "bearish" for d in dets)


def test_sos_requires_consolidation_then_break():
    # flat range then a strong break-up candle with wide spread
    closes = [100.0] * 80
    for k in range(40, 60):
        closes[k] = 100.0 + (k % 3) * 0.05  # tight consolidation
    closes[61] = 104.0  # wide break-up close
    rows = []
    t0 = datetime(2026, 6, 1, tzinfo=UTC)
    for k, c in enumerate(closes):
        rows.append({
            "market_ts": t0 + timedelta(hours=k),
            "open": closes[k - 1] if k else c,
            "high": max(c, closes[k - 1] if k else c) + 0.4,
            "low": min(c, closes[k - 1] if k else c) - 0.4,
            "close": c, "status": "final",
        })
    ctx = build_context("XAUUSD", "1h", rows, rows, rows)
    dets = WyckoffSosSowStrategy().detect(ctx)
    assert any(d.direction == "bullish" for d in dets), "expected SOS bullish break"


def test_exhaustion_needs_extreme_rsi_and_deceleration():
    # monotonic rally that decelerates at the end
    closes = [100.0 + i * 1.0 for i in range(60)]
    closes[55:60] = [158.0, 159.0, 159.5, 159.6, 159.6]  # decelerating tail
    rows = []
    t0 = datetime(2026, 6, 1, tzinfo=UTC)
    for k, c in enumerate(closes):
        rows.append({
            "market_ts": t0 + timedelta(hours=k),
            "open": closes[k - 1] if k else c,
            "high": c + 0.3, "low": c - 0.3, "close": c, "status": "final",
        })
    ctx = build_context("XAUUSD", "1h", rows, rows, rows)
    dets = TrendExhaustionStrategy().detect(ctx)
    assert any(d.direction == "bearish" for d in dets), "expected bearish exhaustion on parabolic run"


def test_vol_regime_reports_neutral_context():
    closes = [100.0] * 130
    rows = []
    t0 = datetime(2026, 6, 1, tzinfo=UTC)
    for k, c in enumerate(closes):
        rows.append({
            "market_ts": t0 + timedelta(hours=k),
            "open": c, "high": c + 0.2, "low": c - 0.2, "close": c, "status": "final",
        })
    ctx = build_context("XAUUSD", "1h", rows, rows, rows)
    dets = VolatilityRegimeStrategy().detect(ctx)
    # flat series: width ~0, contraction context expected (or none) — never a crash
    assert all(d.direction == "neutral" for d in dets)


def test_amd_and_judas_run_without_crash_on_flat_data():
    closes = [100.0] * 150
    rows = []
    t0 = datetime(2026, 6, 1, tzinfo=UTC)
    for k, c in enumerate(closes):
        rows.append({
            "market_ts": t0 + timedelta(hours=k),
            "open": c, "high": c + 0.3, "low": c - 0.3, "close": c, "status": "final",
        })
    ctx = build_context("XAUUSD", "1h", rows, rows, rows)
    assert AmdPowerOfThreeStrategy().detect(ctx) == []
    assert JudasSwingStrategy().detect(ctx) == []
    assert SessionRangeBreakoutStrategy().detect(ctx) == []
