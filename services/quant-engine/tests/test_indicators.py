"""Indicator math tests — hand-computed expectations, no-lookahead checks."""

import math

import pytest

from indicators import (
    adx,
    atr,
    bollinger,
    divergence,
    ema,
    historical_volatility,
    macd,
    roc,
    rsi,
    sma,
    volatility_percentile,
    wilder_smooth,
)


def test_sma_simple():
    assert sma([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]


def test_ema_seed_and_recursion():
    # seed = SMA(1,2,3)=2 ; k = 2/(3+1)=0.5
    # e3 = 2 + 0.5*(4-2) = 3 ; e4 = 3 + 0.5*(5-3) = 4
    assert ema([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]


def test_wilder_smooth_matches_manual():
    vals = [2.0, 2.0, 2.0, 5.0, 5.0]
    out = wilder_smooth(vals, 2)
    # seed = SMA(vals[0:2]) = 2.0 at index period-1 (=1); out[0] stays None
    assert out[1] == 2.0
    # w[3] = 2 + (5-2)/2 = 3.5 ; w[4] = 3.5 + (5-3.5)/2 = 4.25
    assert out[3] == pytest.approx(3.5)
    assert out[4] == pytest.approx(4.25)


def test_rsi_extremes():
    # monotonic rising closes -> RSI 100 (up moves only)
    closes = [float(i) for i in range(1, 30)]
    r = rsi(closes)
    assert r[-1] == 100.0
    # monotonic falling -> RSI ~0
    closes_down = [100.0 - float(i) for i in range(1, 30)]
    r2 = rsi(closes_down)
    assert r2[-1] == pytest.approx(0.0)


def test_atr_known_value():
    # constant range 2, no gaps: TR = 2 every bar -> ATR(3) = 2 from index 2
    highs = [10.0] * 6
    lows = [8.0] * 6
    closes = [9.0] * 6
    a = atr(highs, lows, closes, period=3)
    assert a[2] == pytest.approx(2.0)
    assert a[5] == pytest.approx(2.0)


def test_no_lookahead_series_prefix_invariant():
    """Indicator values computed on a truncated series must equal the prefix of
    the full-series computation — i.e. adding later candles never changes
    earlier values (anti-repaint property)."""
    import random

    rng = random.Random(42)
    closes = [100.0]
    for _ in range(200):
        closes.append(closes[-1] * (1 + rng.uniform(-0.01, 0.01)))
    full_ema = ema(closes, 14)
    full_rsi = rsi(closes)
    prefix_ema = ema(closes[:120], 14)
    prefix_rsi = rsi(closes[:120])
    for i in range(120):
        assert full_ema[i] == prefix_ema[i]
        assert full_rsi[i] == prefix_rsi[i]


def test_macd_shapes():
    closes = [100.0 + math.sin(i / 5) * 2 for i in range(100)]
    line, signal, hist = macd(closes)
    assert line[25] is not None  # defined once slow EMA exists
    assert signal[33] is not None  # 9 EMA of MACD line
    # history: hist = line - signal wherever both defined
    idx = next(i for i in range(len(hist)) if hist[i] is not None)
    assert hist[idx] == pytest.approx(line[idx] - signal[idx])


def test_bollinger_symmetry():
    closes = [10.0] * 30 + [12.0]
    u, m, l = bollinger(closes, period=20, num_std=2.0)
    i = 30
    assert m[i] == pytest.approx(sum(closes[11:31]) / 20)
    assert (u[i] - m[i]) == pytest.approx(m[i] - l[i])


def test_roc():
    out = roc([100.0, 110.0, 120.0, 132.0], period=3)
    assert out[3] == pytest.approx(32.0)


def test_adx_trending_market():
    # strong monotonic trend -> ADX rises, +DI dominates
    n = 120
    highs = [10.0 + i * 0.5 for i in range(n)]
    lows = [9.0 + i * 0.5 for i in range(n)]
    closes = [9.5 + i * 0.5 for i in range(n)]
    adx_v, pdi, mdi = adx(highs, lows, closes)
    assert adx_v[-1] > 25
    assert pdi[-1] > mdi[-1]


def test_historical_volatility_constant_series_zero():
    closes = [100.0] * 40
    hv = historical_volatility(closes, period=20)
    assert hv[-1] == pytest.approx(0.0, abs=1e-9)


def test_volatility_percentile_bounds():
    hv = [float(i) for i in range(1, 60)]
    vp = volatility_percentile(hv, lookback=50)
    assert vp[-1] == pytest.approx(100.0)  # latest is the max of the window


def test_divergence_bullish_detects():
    # Two clean V-shaped price lows: 100→90 (idx 10), up to 95, down to 85 (idx 26).
    # Second price low is LOWER while the mirrored oscillator low is HIGHER
    # → regular bullish divergence.
    closes: list[float] = []
    closes += [100.0 - i for i in range(11)]        # 100 → 90  (idx 0..10)
    closes += [90.0 + i for i in range(1, 6)]       # 91 → 95   (idx 11..15)
    closes += [95.0 - i for i in range(1, 11)]      # 94 → 85   (idx 16..26)
    closes += [85.0 + i for i in range(1, 5)]       # 86 → 89   (idx 27..30)
    osc = [100.0 - c for c in closes]               # mirror: LL in price = HL in osc
    divs = divergence(closes, osc, lookback=60)
    assert any(d.kind == "bullish" for d in divs)
