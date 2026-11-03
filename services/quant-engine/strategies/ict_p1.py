"""P1 ICT strategies (new spec §6): Judas Swing, AMD Power of Three,
ICT Silver Bullet, Session Range Breakout, Liquidity Void.

All detections are deterministic, anchored on closed candles, and reuse the
session ranges computed in indicators.structure (timezone-aware, UTC-based).
"""

from __future__ import annotations

from datetime import datetime

from strategies.base import ALGO_VERSION, CandleContext, Detection, Strategy

ASIA = "asia"


def _ts(ctx: CandleContext, i: int) -> datetime:
    return ctx.times[i]


def _atr(ctx: CandleContext, i: int) -> float:
    return ctx.atr_at(i) or ctx.closes[i] * 0.006


class JudasSwingStrategy(Strategy):
    strategy_id = "ict_judas"
    name = "Judas Swing"
    description = (
        "London-session fake move beyond the Asian range (sweep of Asian high or low), "
        "then a close back inside the range within N bars — the classic manipulation leg "
        "of the Power of Three. Anchored at the reclaim bar."
    )
    default_params: dict = {"max_reclaim_bars": 6, "lookback_bars": 300}

    def detect(self, ctx: CandleContext) -> list[Detection]:
        asia = ctx.sessions.get(ASIA)
        if not asia or asia.get("high") is None or asia.get("low") is None:
            return []
        hi, lo = float(asia["high"]), float(asia["low"])
        out: list[Detection] = []
        max_bars = int(self.default_params["max_reclaim_bars"])
        start = max(1, len(ctx.closes) - int(self.default_params["lookback_bars"]))
        for i in range(start, len(ctx.closes) - 1):
            t = _ts(ctx, i)
            # London session only (07:00–11:00 UTC window vs Judas definition)
            if not (7 <= t.hour < 11):
                continue
            # fake move above Asian high, then close back below it (bearish Judas)
            for j in range(max(1, i - max_bars), i + 1):
                if ctx.highs[j] > hi and ctx.closes[i] < hi and ctx.opens[i] <= hi:
                    out.append(Detection(
                        self.strategy_id, ALGO_VERSION, ctx.symbol, ctx.interval, "bearish",
                        _ts(ctx, i),
                        {"asian_high": hi, "asian_low": lo, "level": hi,
                         "stop": max(ctx.highs[j - max_bars: i + 2]) if j > 0 else hi + _atr(ctx, i)},
                        [f"London Judas: pierced Asian high {hi:.2f} at {_ts(ctx, j).strftime('%H:%M')} then closed back inside at {_ts(ctx, i).strftime('%H:%M')}"],
                        params={},
                    ))
                    break
            # fake move below Asian low, then close back above it (bullish Judas)
            for j in range(max(1, i - max_bars), i + 1):
                if ctx.lows[j] < lo and ctx.closes[i] > lo and ctx.opens[i] >= lo:
                    out.append(Detection(
                        self.strategy_id, ALGO_VERSION, ctx.symbol, ctx.interval, "bullish",
                        _ts(ctx, i),
                        {"asian_high": hi, "asian_low": lo, "level": lo,
                         "stop": min(ctx.lows[j - max_bars: i + 2]) if j > 0 else lo - _atr(ctx, i)},
                        [f"London Judas: pierced Asian low {lo:.2f} at {_ts(ctx, j).strftime('%H:%M')} then closed back inside at {_ts(ctx, i).strftime('%H:%M')}"],
                        params={},
                    ))
                    break
        # dedupe by (direction, anchor)
        seen: set[datetime] = set()
        return [d for d in out if not (d.anchor_time in seen or seen.add(d.anchor_time))]


class AmdPowerOfThreeStrategy(Strategy):
    strategy_id = "ict_amd"
    name = "AMD / Power of Three"
    description = (
        "Accumulation–Manipulation–Distribution on the daily cycle: price ranges "
        "(accumulation), makes a fake move that sweeps the range (manipulation), then "
        "displaces in the opposite direction (distribution). Anchored at the displacement bar."
    )
    default_params: dict = {"range_bars": 12, "displacement_atr": 1.2}

    def detect(self, ctx: CandleContext) -> list[Detection]:
        out: list[Detection] = []
        rb = int(self.default_params["range_bars"])
        disp_atr = float(self.default_params["displacement_atr"])
        for i in range(rb * 2, len(ctx.closes) - 1):
            t = _ts(ctx, i)
            if t.hour != 0:  # evaluate at the daily boundary on hourly data
                continue
            window = slice(i - rb, i)
            w_high, w_low = max(ctx.highs[window]), min(ctx.lows[window])
            w_width = w_high - w_low
            atr = _atr(ctx, i)
            if atr <= 0 or w_width > 3 * atr:
                continue  # not a tight accumulation range
            # manipulation: sweep of either side after the window, then displacement opposite
            for j in range(i, len(ctx.closes) - 1):
                if ctx.highs[j] > w_high and ctx.closes[j] < w_high:
                    # swept high then closed back below → look for bearish displacement
                    k = next((m for m in range(j, len(ctx.closes) - 1)
                              if ctx.opens[m] >= w_high and ctx.closes[m] < w_high - disp_atr * atr), None)
                    if k is not None:
                        out.append(Detection(
                            self.strategy_id, ALGO_VERSION, ctx.symbol, ctx.interval, "bearish",
                            _ts(ctx, k),
                            {"range_high": w_high, "range_low": w_low, "level": w_high,
                             "stop": max(ctx.highs[j:k + 2])},
                            [f"AMD bearish: swept accumulation high {w_high:.2f}, displaced {disp_atr}×ATR lower by {_ts(ctx, k).strftime('%m-%d %H:%M')}"],
                            params={},
                        ))
                        break
                if ctx.lows[j] < w_low and ctx.closes[j] > w_low:
                    k = next((m for m in range(j, len(ctx.closes) - 1)
                              if ctx.opens[m] <= w_low and ctx.closes[m] > w_low + disp_atr * atr), None)
                    if k is not None:
                        out.append(Detection(
                            self.strategy_id, ALGO_VERSION, ctx.symbol, ctx.interval, "bullish",
                            _ts(ctx, k),
                            {"range_high": w_high, "range_low": w_low, "level": w_low,
                             "stop": min(ctx.lows[j:k + 2])},
                            [f"AMD bullish: swept accumulation low {w_low:.2f}, displaced {disp_atr}×ATR higher by {_ts(ctx, k).strftime('%m-%d %H:%M')}"],
                            params={},
                        ))
                        break
                if j - i > 3 * rb:
                    break
        seen: set[datetime] = set()
        return [d for d in out if not (d.anchor_time in seen or seen.add(d.anchor_time))][-20:]


class IctSilverBulletStrategy(Strategy):
    strategy_id = "ict_silver_bullet"
    name = "ICT Silver Bullet"
    description = (
        "Fair Value Gap formed inside the 15:00–16:00 UTC window (10–11 AM New York), "
        "direction of the gap. Anchored at the gap's third candle."
    )
    default_params: dict = {"window_start": 15, "window_end": 16}

    def detect(self, ctx: CandleContext) -> list[Detection]:
        out: list[Detection] = []
        ws, we = int(self.default_params["window_start"]), int(self.default_params["window_end"])
        for i in range(2, len(ctx.closes) - 1):
            t = _ts(ctx, i)
            if not (ws <= t.hour < we):
                continue
            lo3, hi1 = ctx.lows[i], ctx.highs[i - 2]
            if hi1 < lo3:  # bullish FVG inside the window
                out.append(Detection(
                    self.strategy_id, ALGO_VERSION, ctx.symbol, ctx.interval, "bullish",
                    t,
                    {"fvg_low": hi1, "fvg_high": lo3, "level": (hi1 + lo3) / 2,
                     "stop": min(ctx.lows[i - 1: i + 1])},
                    [f"Silver Bullet bullish FVG {hi1:.2f}→{lo3:.2f} formed {t.strftime('%H:%M')} UTC (10–11 NY)"],
                    params={},
                ))
            lo1, hi3 = ctx.lows[i - 2], ctx.highs[i]
            if lo1 > hi3:  # bearish FVG inside the window
                out.append(Detection(
                    self.strategy_id, ALGO_VERSION, ctx.symbol, ctx.interval, "bearish",
                    t,
                    {"fvg_low": hi3, "fvg_high": lo1, "level": (hi3 + lo1) / 2,
                     "stop": max(ctx.highs[i - 1: i + 1])},
                    [f"Silver Bullet bearish FVG {hi3:.2f}→{lo1:.2f} formed {t.strftime('%H:%M')} UTC (10–11 NY)"],
                    params={},
                ))
        return out[-20:]


class SessionRangeBreakoutStrategy(Strategy):
    strategy_id = "ict_session_breakout"
    name = "Session Range Breakout"
    description = (
        "Displacement break of the Asian session range after consolidation. Bullish when a "
        "single candle closes above the Asian high with body ≥ 1×ATR; bearish the mirror. "
        "Anchored at the breakout candle."
    )
    default_params: dict = {"body_atr": 1.0, "lookback_bars": 300}

    def detect(self, ctx: CandleContext) -> list[Detection]:
        asia = ctx.sessions.get(ASIA)
        if not asia or asia.get("high") is None:
            return []
        hi, lo = float(asia["high"]), float(asia["low"])
        out: list[Detection] = []
        min_body = float(self.default_params["body_atr"])
        start = max(1, len(ctx.closes) - int(self.default_params["lookback_bars"]))
        for i in range(start, len(ctx.closes) - 1):
            atr = _atr(ctx, i)
            body = abs(ctx.closes[i] - ctx.opens[i])
            if body < min_body * atr:
                continue
            if ctx.closes[i] > hi and ctx.opens[i] <= hi:
                out.append(Detection(
                    self.strategy_id, ALGO_VERSION, ctx.symbol, ctx.interval, "bullish", _ts(ctx, i),
                    {"asian_high": hi, "asian_low": lo, "level": hi, "stop": min(ctx.lows[i - 3: i + 1]) or lo},
                    [f"Bullish displacement close {ctx.closes[i]:.2f} above Asian high {hi:.2f} (body {body:.2f} = {body / atr:.1f}×ATR)"],
                    params={},
                ))
            elif ctx.closes[i] < lo and ctx.opens[i] >= lo:
                out.append(Detection(
                    self.strategy_id, ALGO_VERSION, ctx.symbol, ctx.interval, "bearish", _ts(ctx, i),
                    {"asian_high": hi, "asian_low": lo, "level": lo, "stop": max(ctx.highs[i - 3: i + 1]) or hi},
                    [f"Bearish displacement close {ctx.closes[i]:.2f} below Asian low {lo:.2f} (body {body:.2f} = {body / atr:.1f}×ATR)"],
                    params={},
                ))
        seen: set[datetime] = set()
        return [d for d in out if not (d.anchor_time in seen or seen.add(d.anchor_time))]


class LiquidityVoidStrategy(Strategy):
    strategy_id = "ict_liquidity_void"
    name = "Liquidity Void"
    description = (
        "A single displacement candle (body ≥ 1.5×ATR) leaves an unbalanced one-candle "
        "inefficiency: price is expected to rebalance toward the void. Direction = opposite "
        "of the void candle (mean reversion). Anchored at the candle after the void."
    )
    default_params = {"body_atr": 1.5, "lookback_bars": 200}

    def detect(self, ctx: CandleContext) -> list[Detection]:
        out: list[Detection] = []
        min_body = float(self.default_params["body_atr"])
        start = max(2, len(ctx.closes) - int(self.default_params["lookback_bars"]))
        for i in range(start, len(ctx.closes) - 1):
            atr = _atr(ctx, i)
            body = abs(ctx.closes[i] - ctx.opens[i])
            if body < min_body * atr:
                continue
            bull_void = ctx.closes[i] > ctx.opens[i]
            # void bounds: the wick-free span the candle left behind
            void_low, void_high = (ctx.opens[i], ctx.closes[i]) if bull_void else (ctx.closes[i], ctx.opens[i])
            direction = "bearish" if bull_void else "bullish"
            out.append(Detection(
                self.strategy_id, ALGO_VERSION, ctx.symbol, ctx.interval, direction, _ts(ctx, i + 1),
                {"void_low": void_low, "void_high": void_high, "level": (void_low + void_high) / 2,
                 "stop": (void_low - atr) if direction == "bullish" else (void_high + atr)},
                [f"{'Bullish' if direction == 'bullish' else 'Bearish'} void: {body:.2f} body ({body / atr:.1f}×ATR) left {void_low:.2f}–{void_high:.2f} unbalanced"],
                params={},
            ))
        return out[-20:]
