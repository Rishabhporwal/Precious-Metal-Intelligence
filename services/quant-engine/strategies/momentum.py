"""Momentum & trend-following strategy family (enhancement spec §2.1).

Independent of SMC/ICT — these exist so a strong one-way move produces a
signal even when no textbook pattern formed. All detections are deterministic
and anchored on closed candles.

State-style strategies (EMA alignment, MTF alignment) emit on TRANSITION into
the aligned state (plus re-confirmation after a gap) so they don't flood the
detection store with one row per bar.
"""

from __future__ import annotations

from datetime import datetime

from indicators.structure import detect_swings, label_swings
from strategies.base import ALGO_VERSION, CandleContext, Detection, Strategy


def _ts(ctx: CandleContext, i: int) -> datetime:
    return ctx.times[i]


def _atr(ctx: CandleContext, i: int) -> float:
    return ctx.atr_at(i) or ctx.closes[i] * 0.006


def _ema(vals: list[float], n: int) -> list[float | None]:
    if len(vals) < n:
        return [None] * len(vals)
    k = 2 / (n + 1)
    out: list[float | None] = [None] * (n - 1)
    e = sum(vals[:n]) / n
    out.append(e)
    for v in vals[n:]:
        e = v * k + e * (1 - k)
        out.append(e)
    return out


def _dedupe(out: list[Detection]) -> list[Detection]:
    seen: set[datetime] = set()
    return [d for d in out if not (d.anchor_time in seen or seen.add(d.anchor_time))][-20:]


class TrendContinuationStrategy(Strategy):
    strategy_id = "mom_trend_cont"
    name = "Strong Trend Continuation"
    description = (
        "Run of ≥ N consecutive higher closes (or lower) with expanding average body, "
        "then a continuation close in the same direction above the prior bar's high "
        "(below for shorts). Directional momentum signal — no SMC confirmation required."
    )
    default_params = {"min_run": 5, "body_expansion": 1.1, "lookback": 300}

    def detect(self, ctx: CandleContext) -> list[Detection]:
        out: list[Detection] = []
        min_run = int(self.default_params["min_run"])
        exp = float(self.default_params["body_expansion"])
        start = max(min_run + 1, len(ctx.closes) - int(self.default_params["lookback"]))
        for i in range(start, len(ctx.closes) - 1):
            run = ctx.closes[i - min_run: i + 1]
            ups = sum(1 for k in range(1, len(run)) if run[k] > run[k - 1])
            bodies = [abs(ctx.closes[k] - ctx.opens[k]) for k in range(i - min_run, i + 1)]
            first_half = sum(bodies[: len(bodies) // 2]) / max(1, len(bodies) // 2)
            second_half = sum(bodies[len(bodies) // 2:]) / max(1, len(bodies) - len(bodies) // 2)
            if ups >= min_run - 1 and second_half > first_half * exp and ctx.closes[i] > ctx.highs[i - 1]:
                out.append(Detection(
                    strategy_id=self.strategy_id, algo_version=ALGO_VERSION, symbol=ctx.symbol,
                    interval=ctx.interval, direction="bullish", anchor_time=_ts(ctx, i),
                    levels={"run_low": min(ctx.lows[i - min_run: i + 1]), "level": ctx.closes[i],
                            "stop": min(ctx.lows[i - min_run: i + 1])},
                    evidence=[f"Bullish continuation: {min_run}-bar advance, bodies expanding {second_half / first_half:.1f}×, closed above prior high"],
                    params={},
                ))
            downs = sum(1 for k in range(1, len(run)) if run[k] < run[k - 1])
            if downs >= min_run - 1 and second_half > first_half * exp and ctx.closes[i] < ctx.lows[i - 1]:
                out.append(Detection(
                    strategy_id=self.strategy_id, algo_version=ALGO_VERSION, symbol=ctx.symbol,
                    interval=ctx.interval, direction="bearish", anchor_time=_ts(ctx, i),
                    levels={"run_high": max(ctx.highs[i - min_run: i + 1]), "level": ctx.closes[i],
                            "stop": max(ctx.highs[i - min_run: i + 1])},
                    evidence=[f"Bearish continuation: {min_run}-bar decline, bodies expanding {second_half / first_half:.1f}×, closed below prior low"],
                    params={},
                ))
        return _dedupe(out)


class BreakoutRetestStrategy(Strategy):
    strategy_id = "mom_breakout_retest"
    name = "Breakout and Retest"
    description = (
        "Price closes beyond an N-bar resistance/support level, then within M bars pulls "
        "back to the level and holds it (a close on the breakout side of the level after "
        "touching it). Anchored at the holding bar."
    )
    default_params = {"range_bars": 20, "retest_bars": 10, "lookback": 400}

    def detect(self, ctx: CandleContext) -> list[Detection]:
        out: list[Detection] = []
        rb = int(self.default_params["range_bars"])
        mb = int(self.default_params["retest_bars"])
        start = max(rb + 1, len(ctx.closes) - int(self.default_params["lookback"]))
        for i in range(start, len(ctx.closes) - mb - 1):
            level = max(ctx.highs[i - rb: i])
            if ctx.closes[i] > level and ctx.opens[i] <= level:
                # bullish breakout — look for a retest that holds within mb bars
                for j in range(i + 1, min(i + mb + 1, len(ctx.closes) - 1)):
                    if ctx.lows[j] <= level * 1.002 and ctx.closes[j] > level:
                        out.append(Detection(
                            strategy_id=self.strategy_id, algo_version=ALGO_VERSION, symbol=ctx.symbol,
                            interval=ctx.interval, direction="bullish", anchor_time=_ts(ctx, j),
                            levels={"breakout_level": level, "level": level,
                                    "stop": min(ctx.lows[j - 3: j + 1]) or level - _atr(ctx, j)},
                            evidence=[f"Bullish breakout {level:.2f} at {_ts(ctx, i).strftime('%m-%d %H:%M')}, retest held at {_ts(ctx, j).strftime('%m-%d %H:%M')}"],
                            params={},
                        ))
                        break
                    if ctx.closes[j] < level - _atr(ctx, j):
                        break  # failed breakout — no signal
        return _dedupe(out)


class RangeBreakoutStrategy(Strategy):
    strategy_id = "mom_range_breakout"
    name = "Range Breakout"
    description = (
        "Close beyond an N-bar range on an expanded bar (body ≥ 1×ATR) — the Donchian-style "
        "breakout. Anchored at the breakout close."
    )
    default_params = {"range_bars": 24, "body_atr": 1.0, "lookback": 400}

    def detect(self, ctx: CandleContext) -> list[Detection]:
        out: list[Detection] = []
        rb = int(self.default_params["range_bars"])
        min_body = float(self.default_params["body_atr"])
        start = max(rb + 1, len(ctx.closes) - int(self.default_params["lookback"]))
        for i in range(start, len(ctx.closes) - 1):
            atr = _atr(ctx, i)
            body = abs(ctx.closes[i] - ctx.opens[i])
            hi = max(ctx.highs[i - rb: i])
            lo = min(ctx.lows[i - rb: i])
            if body >= min_body * atr and ctx.closes[i] > hi:
                out.append(Detection(
                    strategy_id=self.strategy_id, algo_version=ALGO_VERSION, symbol=ctx.symbol,
                    interval=ctx.interval, direction="bullish", anchor_time=_ts(ctx, i),
                    levels={"range_high": hi, "range_low": lo, "level": hi,
                            "stop": max(lo, ctx.closes[i] - 1.5 * atr)},
                    evidence=[f"Bullish range breakout: closed {ctx.closes[i]:.2f} above {rb}-bar high {hi:.2f} on {body / atr:.1f}×ATR body"],
                    params={},
                ))
            elif body >= min_body * atr and ctx.closes[i] < lo:
                out.append(Detection(
                    strategy_id=self.strategy_id, algo_version=ALGO_VERSION, symbol=ctx.symbol,
                    interval=ctx.interval, direction="bearish", anchor_time=_ts(ctx, i),
                    levels={"range_high": hi, "range_low": lo, "level": lo,
                            "stop": min(hi, ctx.closes[i] + 1.5 * atr)},
                    evidence=[f"Bearish range breakout: closed {ctx.closes[i]:.2f} below {rb}-bar low {lo:.2f} on {body / atr:.1f}×ATR body"],
                    params={},
                ))
        return _dedupe(out)


class MomentumExpansionStrategy(Strategy):
    strategy_id = "mom_expansion"
    name = "Momentum Expansion"
    description = (
        "Three consecutive same-direction closes with each body larger than the last and "
        "the final body ≥ 1×ATR — accelerating momentum. Anchored at the third bar."
    )
    default_params = {"min_body_atr": 1.0}

    def detect(self, ctx: CandleContext) -> list[Detection]:
        out: list[Detection] = []
        min_body = float(self.default_params["min_body_atr"])
        for i in range(3, len(ctx.closes) - 1):
            atr = _atr(ctx, i)
            b1 = abs(ctx.closes[i - 2] - ctx.opens[i - 2])
            b2 = abs(ctx.closes[i - 1] - ctx.opens[i - 1])
            b3 = abs(ctx.closes[i] - ctx.opens[i])
            bull = ctx.closes[i - 2] > ctx.opens[i - 2] and ctx.closes[i - 1] > ctx.opens[i - 1] and ctx.closes[i] > ctx.opens[i]
            bear = ctx.closes[i - 2] < ctx.opens[i - 2] and ctx.closes[i - 1] < ctx.opens[i - 1] and ctx.closes[i] < ctx.opens[i]
            if bull and b3 > b2 > b1 and b3 >= min_body * atr:
                out.append(Detection(
                    strategy_id=self.strategy_id, algo_version=ALGO_VERSION, symbol=ctx.symbol,
                    interval=ctx.interval, direction="bullish", anchor_time=_ts(ctx, i),
                    levels={"level": ctx.closes[i], "stop": min(ctx.lows[i - 2: i + 1])},
                    evidence=[f"Momentum expansion: 3 accelerating bullish bodies, last {b3:.2f} = {b3 / atr:.1f}×ATR"],
                    params={},
                ))
            if bear and b3 > b2 > b1 and b3 >= min_body * atr:
                out.append(Detection(
                    strategy_id=self.strategy_id, algo_version=ALGO_VERSION, symbol=ctx.symbol,
                    interval=ctx.interval, direction="bearish", anchor_time=_ts(ctx, i),
                    levels={"level": ctx.closes[i], "stop": max(ctx.highs[i - 2: i + 1])},
                    evidence=[f"Momentum expansion: 3 accelerating bearish bodies, last {b3:.2f} = {b3 / atr:.1f}×ATR"],
                    params={},
                ))
        return _dedupe(out)


class EmaAlignmentStrategy(Strategy):
    strategy_id = "mom_ema_align"
    name = "EMA Trend Alignment"
    description = (
        "EMA20 > EMA50 > EMA200 with price above EMA20 (bullish stack; mirrored bearish). "
        "State strategy: emits on TRANSITION into alignment, not every bar."
    )
    default_params = {}

    def detect(self, ctx: CandleContext) -> list[Detection]:
        e20 = _ema(ctx.closes, 20)
        e50 = _ema(ctx.closes, 50)
        e200 = _ema(ctx.closes, 200)
        out: list[Detection] = []
        prev_state = 0  # -1 bear, 0 none, 1 bull
        for i in range(len(ctx.closes) - 1, 1, -1):
            v20, v50, v200 = e20[i], e50[i], e200[i]
            if v20 is None or v50 is None or v200 is None:
                continue
            state = 1 if (v20 > v50 > v200 and ctx.closes[i] > v20) else -1 if (v20 < v50 < v200 and ctx.closes[i] < v20) else 0
            if state != 0 and state != prev_state:
                out.append(Detection(
                    strategy_id=self.strategy_id, algo_version=ALGO_VERSION, symbol=ctx.symbol,
                    interval=ctx.interval,
                    direction="bullish" if state == 1 else "bearish",
                    anchor_time=_ts(ctx, i),
                    levels={"ema20": round(v20, 4), "ema50": round(v50, 4),
                            "level": round(v20, 4), "stop": round(v50, 4)},
                    evidence=[f"{'Bullish' if state == 1 else 'Bearish'} EMA stack established (20>50>200, price {'above' if state == 1 else 'below'} EMA20)"],
                    params={},
                ))
            prev_state = state
        return list(reversed(out))[-6:]


class HigherHighsStrategy(Strategy):
    strategy_id = "mom_hh_hl"
    name = "Higher High / Higher Low Continuation"
    description = (
        "Structure labels show ≥ 2 consecutive HH+HL sequences (bullish) or LH+LL "
        "(bearish) with the latest swing confirmed. Anchored at the latest confirmed swing."
    )
    default_params = {}

    def detect(self, ctx: CandleContext) -> list[Detection]:
        swings = detect_swings(ctx.highs, ctx.lows)
        labels = label_swings(swings)  # [(swing idx, "HH"/"HL"/"LH"/"LL")]
        if len(labels) < 4:
            return []
        tail = [l for _, l in labels[-4:]]
        last_idx = labels[-1][0]
        if last_idx >= len(ctx.closes) - 2:
            return []  # swing not yet confirmed by right-side bars
        atr = _atr(ctx, last_idx)
        out: list[Detection] = []
        if tail.count("HH") + tail.count("HL") >= 3:
            out.append(Detection(
                strategy_id=self.strategy_id, algo_version=ALGO_VERSION, symbol=ctx.symbol,
                interval=ctx.interval, direction="bullish", anchor_time=_ts(ctx, last_idx),
                levels={"level": ctx.closes[last_idx],
                        "stop": min(ctx.lows[max(0, last_idx - 5): last_idx + 1]) if last_idx >= 5 else ctx.closes[last_idx] - 2 * atr},
                evidence=[f"HH/HL continuation: recent labels {tail}"],
                params={},
            ))
        if tail.count("LH") + tail.count("LL") >= 3:
            out.append(Detection(
                strategy_id=self.strategy_id, algo_version=ALGO_VERSION, symbol=ctx.symbol,
                interval=ctx.interval, direction="bearish", anchor_time=_ts(ctx, last_idx),
                levels={"level": ctx.closes[last_idx],
                        "stop": max(ctx.highs[max(0, last_idx - 5): last_idx + 1]) if last_idx >= 5 else ctx.closes[last_idx] + 2 * atr},
                evidence=[f"LH/LL continuation: recent labels {tail}"],
                params={},
            ))
        return out


class PullbackInTrendStrategy(Strategy):
    strategy_id = "mom_pullback"
    name = "Pullback Entry in Strong Trends"
    description = (
        "In an established EMA-aligned trend, price pulls back to touch EMA20/EMA50 and "
        "then prints a resumption close in the trend direction. Anchored at the resumption bar."
    )
    default_params = {}

    def detect(self, ctx: CandleContext) -> list[Detection]:
        e20 = _ema(ctx.closes, 20)
        e50 = _ema(ctx.closes, 50)
        out: list[Detection] = []
        for i in range(60, len(ctx.closes) - 1):
            v20, v50 = e20[i], e50[i]
            if v20 is None or v50 is None:
                continue
            atr = _atr(ctx, i)
            bull_trend = v20 > v50
            touched = ctx.lows[i] <= v20 if bull_trend else ctx.highs[i] >= v20
            resumed = ctx.closes[i] > ctx.closes[i - 1] and ctx.closes[i] > v20 if bull_trend else (
                ctx.closes[i] < ctx.closes[i - 1] and ctx.closes[i] < v20
            )
            if touched and resumed:
                direction = "bullish" if bull_trend else "bearish"
                out.append(Detection(
                    strategy_id=self.strategy_id, algo_version=ALGO_VERSION, symbol=ctx.symbol,
                    interval=ctx.interval, direction=direction, anchor_time=_ts(ctx, i),
                    levels={"ema20": round(v20, 4), "ema50": round(v50, 4), "level": round(v20, 4),
                            "stop": round((v50 - 1 * atr) if bull_trend else (v50 + 1 * atr), 4)},
                    evidence=[f"{'Bullish' if bull_trend else 'Bearish'} trend pullback: touched EMA20 {v20:.2f}, resumption close {ctx.closes[i]:.2f}"],
                    params={},
                ))
        return _dedupe(out)


class MultiTimeframeAlignmentStrategy(Strategy):
    strategy_id = "mom_mtf_align"
    name = "Multi-Timeframe Trend Alignment"
    description = (
        "Daily, 4H-proxy and hourly trends all point the same way (structure trend + "
        "hourly EMA stack). State strategy: emits on transition into full alignment."
    )
    default_params = {}

    def detect(self, ctx: CandleContext) -> list[Detection]:
        swings = detect_swings(ctx.highs, ctx.lows)
        labels = label_swings(swings)
        tail = [l for _, l in labels[-6:]]
        ups = tail.count("HH") + tail.count("HL")
        downs = tail.count("LH") + tail.count("LL")
        daily_dir = "up" if ups >= 4 else "down" if downs >= 4 else "sideways"
        e20 = _ema(ctx.closes, 20)
        e50 = _ema(ctx.closes, 50)
        i = len(ctx.closes) - 2
        if e20[i] is None or e50[i] is None:
            return []
        hourly_dir = "up" if e20[i] > e50[i] else "down"
        state = None
        if daily_dir == "up" and hourly_dir == "up":
            state = "bullish"
        elif daily_dir == "down" and hourly_dir == "down":
            state = "bearish"
        if state is None:
            return []
        # only emit when the most recent prior MTF check differs — approximate by
        # checking the state 24 bars earlier
        j = max(60, i - 24)
        e20j, e50j = _ema(ctx.closes, 20)[j], _ema(ctx.closes, 50)[j]
        prev_hourly = "up" if (e20j is not None and e50j is not None and e20j > e50j) else "down"
        prev_state = "bullish" if (daily_dir == "up" and prev_hourly == "up") else "bearish" if (daily_dir == "down" and prev_hourly == "down") else None
        if state == prev_state and i - j <= 26:
            return []  # already aligned a day ago — no transition
        atr = _atr(ctx, i)
        return [Detection(
            strategy_id=self.strategy_id, algo_version=ALGO_VERSION, symbol=ctx.symbol,
            interval=ctx.interval, direction=state, anchor_time=_ts(ctx, i),
            levels={"level": ctx.closes[i],
                    "stop": ctx.closes[i] - 2 * atr if state == "bullish" else ctx.closes[i] + 2 * atr},
            evidence=[f"Multi-TF alignment: daily trend {daily_dir} + hourly EMAs {hourly_dir}"],
            params={},
        )]
