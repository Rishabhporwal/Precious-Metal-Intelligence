"""Deterministic technical indicators.

Pure functions over float sequences. Rules enforced everywhere:
- Output at index i uses only data at indices <= i (no future leakage).
- Warm-up positions are None until the indicator is defined.
- Wilder smoothing where the industry standard requires it (RSI, ATR, ADX).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

Series = list[float | None]


def sma(values: list[float], period: int) -> Series:
    if period <= 0:
        raise ValueError("period must be positive")
    out: Series = [None] * len(values)
    running = 0.0
    for i, v in enumerate(values):
        running += v
        if i >= period:
            running -= values[i - period]
        if i >= period - 1:
            out[i] = running / period
    return out


def ema(values: list[float], period: int) -> Series:
    if period <= 0:
        raise ValueError("period must be positive")
    out: Series = [None] * len(values)
    if len(values) < period:
        return out
    k = 2.0 / (period + 1.0)
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = prev + k * (values[i] - prev)
        out[i] = prev
    return out


def wilder_smooth(values: list[float], period: int) -> Series:
    """Wilder's smoothing (RMA): first value = SMA of first `period`, then r = prev + (x - prev)/period."""
    out: Series = [None] * len(values)
    if len(values) < period:
        return out
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(values)):
        prev = prev + (values[i] - prev) / period
        out[i] = prev
    return out


def rsi(closes: list[float], period: int = 14) -> Series:
    if len(closes) <= period:
        return [None] * len(closes)
    gains: list[float] = [0.0]
    losses: list[float] = [0.0]
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = wilder_smooth(gains, period)
    avg_loss = wilder_smooth(losses, period)
    out: Series = [None] * len(closes)
    for i in range(len(closes)):
        g, l = avg_gain[i], avg_loss[i]
        if g is None or l is None:
            continue
        if l == 0:
            out[i] = 100.0 if g > 0 else 50.0
        else:
            rs = g / l
            out[i] = 100.0 - 100.0 / (1.0 + rs)
    return out


def true_ranges(highs: list[float], lows: list[float], closes: list[float]) -> list[float]:
    trs = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    return trs


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> Series:
    trs = true_ranges(highs, lows, closes)
    return wilder_smooth(trs, period)


def macd(
    closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[Series, Series, Series]:
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    line: Series = [
        (f - s) if (f is not None and s is not None) else None
        for f, s in zip(ema_fast, ema_slow, strict=True)
    ]
    defined_idx = next((i for i, v in enumerate(line) if v is not None), None)
    compact: list[float] = []
    compact_map: list[int] = []
    if defined_idx is not None:
        for i in range(defined_idx, len(line)):
            v = line[i]
            if v is not None:
                compact.append(v)
                compact_map.append(i)
    sig_compact = ema(compact, signal)
    signal_line: Series = [None] * len(closes)
    for j, i in enumerate(compact_map):
        if sig_compact[j] is not None:
            signal_line[i] = sig_compact[j]
    hist: Series = [
        (l - s) if (l is not None and s is not None) else None
        for l, s in zip(line, signal_line, strict=True)
    ]
    return line, signal_line, hist


def stochastic(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    k_period: int = 14,
    d_period: int = 3,
) -> tuple[Series, Series]:
    k: Series = [None] * len(closes)
    for i in range(k_period - 1, len(closes)):
        hh = max(highs[i - k_period + 1 : i + 1])
        ll = min(lows[i - k_period + 1 : i + 1])
        k[i] = 100.0 * (closes[i] - ll) / (hh - ll) if hh != ll else 50.0
    k_compact = [(i, v) for i, v in enumerate(k) if v is not None]
    d_values = sma([v for _, v in k_compact], d_period)
    d: Series = [None] * len(closes)
    for (i, _), dv in zip(k_compact, d_values, strict=False):
        if dv is not None:
            d[i] = dv
    return k, d


def roc(closes: list[float], period: int = 9) -> Series:
    out: Series = [None] * len(closes)
    for i in range(period, len(closes)):
        base = closes[i - period]
        out[i] = (closes[i] / base - 1.0) * 100.0 if base != 0 else None
    return out


def adx(
    highs: list[float], lows: list[float], closes: list[float], period: int = 14
) -> tuple[Series, Series, Series]:
    """Returns (adx, plus_di, minus_di), Wilder-smoothed."""
    n = len(closes)
    plus_dm: list[float] = [0.0]
    minus_dm: list[float] = [0.0]
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
    trs = true_ranges(highs, lows, closes)
    atr_s = wilder_smooth(trs, period)
    pdm_s = wilder_smooth(plus_dm, period)
    mdm_s = wilder_smooth(minus_dm, period)
    dx: list[float] = []
    dx_map: list[int] = []
    plus_di: Series = [None] * n
    minus_di: Series = [None] * n
    for i in range(n):
        a, p, m = atr_s[i], pdm_s[i], mdm_s[i]
        if a in (None, 0.0) or p is None or m is None:
            continue
        pdi = 100.0 * p / a
        mdi = 100.0 * m / a
        plus_di[i] = pdi
        minus_di[i] = mdi
        denom = pdi + mdi
        if denom > 0:
            dx.append(100.0 * abs(pdi - mdi) / denom)
            dx_map.append(i)
    adx_s = wilder_smooth(dx, period)
    adx_out: Series = [None] * n
    for j, v in enumerate(adx_s):
        if v is not None and j < len(dx_map):
            adx_out[dx_map[j]] = v
    return adx_out, plus_di, minus_di


def bollinger(
    closes: list[float], period: int = 20, num_std: float = 2.0
) -> tuple[Series, Series, Series]:
    mid = sma(closes, period)
    upper: Series = [None] * len(closes)
    lower: Series = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1 : i + 1]
        m = mid[i]
        if m is None:
            continue
        sd = math.sqrt(sum((v - m) ** 2 for v in window) / period)
        upper[i] = m + num_std * sd
        lower[i] = m - num_std * sd
    return upper, mid, lower


def log_returns(closes: list[float]) -> list[float]:
    return [
        math.log(closes[i] / closes[i - 1])
        for i in range(1, len(closes))
        if closes[i - 1] > 0 and closes[i] > 0
    ]


def historical_volatility(closes: list[float], period: int = 20, annualize_days: int = 252) -> Series:
    """Annualized std-dev of log returns over a trailing window (%)."""
    rets = log_returns(closes)  # rets[i] corresponds to closes index i+1
    out: Series = [None] * len(closes)
    for i in range(period, len(closes)):
        window = rets[i - period : i]  # returns up to and including bar i
        mean = sum(window) / len(window)
        var = sum((r - mean) ** 2 for r in window) / period
        out[i] = math.sqrt(var) * math.sqrt(annualize_days) * 100.0
    return out


def realized_volatility(closes: list[float], period: int = 20, annualize_days: int = 252) -> Series:
    """Annualized root-mean-square of log returns (no de-meaning) (%)."""
    rets = log_returns(closes)
    out: Series = [None] * len(closes)
    for i in range(period, len(closes)):
        window = rets[i - period : i]
        var = sum(r * r for r in window) / period
        out[i] = math.sqrt(var) * math.sqrt(annualize_days) * 100.0
    return out


def volatility_percentile(hv: Series, lookback: int = 252) -> Series:
    """Percentile rank (0-100) of the current HV within the trailing `lookback` HV values."""
    defined = [(i, v) for i, v in enumerate(hv) if v is not None]
    out: Series = [None] * len(hv)
    for j, (i, v) in enumerate(defined):
        window = [w for _, w in defined[max(0, j - lookback + 1) : j + 1]]
        if len(window) < 20:
            continue
        below = sum(1 for w in window if w <= v)
        out[i] = 100.0 * below / len(window)
    return out


@dataclass(frozen=True)
class Divergence:
    kind: str  # "bullish" | "bearish"
    oscillator: str  # "rsi" | "macd_hist"
    index_a: int
    index_b: int
    detail: str


def divergence(
    closes: list[float],
    oscillator: Series,
    lookback: int = 60,
    price_tol: float = 0.0,
) -> list[Divergence]:
    """Regular divergence between price pivots and oscillator pivots.

    Uses only confirmed data: pivots are detected with a 2-bar right shoulder,
    and evaluation window ends at the last index — still, callers must only
    trust the final detection after it has had its confirmation bars.
    """
    n = len(closes)
    out: list[Divergence] = []
    start = max(2, n - lookback)
    # price pivots (2-bar fractal)
    price_pivots_high = [
        i for i in range(start, n - 2) if closes[i] > closes[i - 1] and closes[i] > closes[i + 1] and closes[i] >= closes[i - 2] and closes[i] >= closes[i + 2]
    ]
    price_pivots_low = [
        i for i in range(start, n - 2) if closes[i] < closes[i - 1] and closes[i] < closes[i + 1] and closes[i] <= closes[i - 2] and closes[i] <= closes[i + 2]
    ]
    osc_at = lambda i: oscillator[i]

    def osc_pivots(kind: str) -> list[int]:
        res = []
        for i in range(start, n - 2):
            v = osc_at(i)
            if v is None:
                continue
            a, b = osc_at(i - 1), osc_at(i + 1)
            c, d = osc_at(i - 2), osc_at(i + 2)
            if a is None or b is None or c is None or d is None:
                continue
            if kind == "high" and v > a and v > b and v >= c and v >= d:
                res.append(i)
            if kind == "low" and v < a and v < b and v <= c and v <= d:
                res.append(i)
        return res

    osc_highs = osc_pivots("high")
    osc_lows = osc_pivots("low")

    def nearest(pivots: list[int], i: int, window: int = 6) -> int | None:
        cands = [p for p in pivots if abs(p - i) <= window]
        return min(cands, key=lambda p: abs(p - i)) if cands else None

    # bearish regular: price higher high, oscillator lower high
    for i in price_pivots_high:
        j = nearest(osc_highs, i)
        if j is None:
            continue
        ov_j, ov_i = osc_at(j), osc_at(i)
        if ov_j is None or ov_i is None:
            continue
        if closes[i] > closes[j] * (1 + price_tol) and ov_i < ov_j:
            out.append(Divergence("bearish", "osc", i, j, "price HH, oscillator LH"))
    # bullish regular: price lower low, oscillator higher low
    for i in price_pivots_low:
        j = nearest(osc_lows, i)
        if j is None:
            continue
        ov_j, ov_i = osc_at(j), osc_at(i)
        if ov_j is None or ov_i is None:
            continue
        if closes[i] < closes[j] * (1 - price_tol) and ov_i > ov_j:
            out.append(Divergence("bullish", "osc", i, j, "price LL, oscillator HL"))
    return out
