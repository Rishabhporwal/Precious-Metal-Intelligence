"""P1 Wyckoff + quantitative strategies (new spec §6).

- Wyckoff SOS / SOW: sign of strength / weakness — a range break on a
  widened-spread candle after a prolonged consolidation that contained a
  spring/upthrust context.
- Hidden RSI Divergence: trend-continuation divergence.
- Trend Exhaustion: extended trend + momentum deceleration at an RSI extreme.
- Volatility Expansion / Contraction: Bollinger-width squeeze and expansion.
"""

from __future__ import annotations

from datetime import datetime

from indicators.oscillators import rsi as rsi_series
from strategies.base import ALGO_VERSION, CandleContext, Detection, Strategy


def _ts(ctx: CandleContext, i: int) -> datetime:
    return ctx.times[i]


def _atr_at(ctx: CandleContext, i: int) -> float:
    return ctx.atr_at(i) or ctx.closes[i] * 0.006


class WyckoffSosSowStrategy(Strategy):
    strategy_id = "wyckoff_sos_sow"
    name = "Wyckoff SOS / SOW"
    description = (
        "Sign of Strength / Sign of Weakness: after ≥ N bars of sideways range "
        "(consolidation), a candle closes beyond the range on a spread ≥ 1.2×ATR. "
        "SOS is bullish (break up), SOW bearish (break down). Anchored at the break bar."
    )
    default_params = {"range_bars": 15, "max_range_atr": 2.5, "spread_atr": 1.2}

    def detect(self, ctx: CandleContext) -> list[Detection]:
        out: list[Detection] = []
        rb = int(self.default_params["range_bars"])
        max_width = float(self.default_params["max_range_atr"])
        min_spread = float(self.default_params["spread_atr"])
        for i in range(rb, len(ctx.closes) - 1):
            window = slice(i - rb, i)
            r_high, r_low = max(ctx.highs[window]), min(ctx.lows[window])
            width = r_high - r_low
            atr = _atr_at(ctx, i)
            if width > max_width * atr:
                continue  # not a consolidation
            body = abs(ctx.closes[i] - ctx.opens[i])
            if body < min_spread * atr:
                continue
            if ctx.closes[i] > r_high:
                out.append(Detection(
                    strategy_id=self.strategy_id, algo_version=ALGO_VERSION, symbol=ctx.symbol,
                    interval=ctx.interval, direction="bullish", anchor_time=_ts(ctx, i),
                    levels={"range_high": r_high, "range_low": r_low, "level": r_high,
                            "stop": r_low or ctx.closes[i] - 2 * atr},
                    evidence=[f"SOS: {rb}-bar range {r_low:.2f}–{r_high:.2f} broken up on {body / atr:.1f}×ATR spread"],
                    params={},
                ))
            elif ctx.closes[i] < r_low:
                out.append(Detection(
                    strategy_id=self.strategy_id, algo_version=ALGO_VERSION, symbol=ctx.symbol,
                    interval=ctx.interval, direction="bearish", anchor_time=_ts(ctx, i),
                    levels={"range_high": r_high, "range_low": r_low, "level": r_low,
                            "stop": r_high or ctx.closes[i] + 2 * atr},
                    evidence=[f"SOW: {rb}-bar range {r_low:.2f}–{r_high:.2f} broken down on {body / atr:.1f}×ATR spread"],
                    params={},
                ))
        seen: set[datetime] = set()
        return [d for d in out if not (d.anchor_time in seen or seen.add(d.anchor_time))][-20:]


class HiddenDivergenceStrategy(Strategy):
    strategy_id = "quant_hidden_div"
    name = "Hidden RSI Divergence"
    description = (
        "Trend-continuation divergence: in an uptrend price makes a higher low while RSI "
        "makes a lower low (hidden bullish); mirror for downtrends. Uses swing lows/highs "
        "from the structure engine and RSI(14) at those bars."
    )
    default_params = {"lookback_swings": 6, "rsi_ob": 40, "rsi_os": 60}

    def detect(self, ctx: CandleContext) -> list[Detection]:
        rs = rsi_series(ctx.closes, 14)
        lows = [(i, v) for i, v in enumerate(ctx.swings) if v.kind == "low" and i >= len(ctx.closes) - 400]
        highs = [(i, v) for i, v in enumerate(ctx.swings) if v.kind == "high" and i >= len(ctx.closes) - 400]
        out: list[Detection] = []
        max_sw = int(self.default_params["lookback_swings"])
        # hidden bullish: two consecutive swing lows, price HL, RSI lower low below mid
        low_pairs = [(lows[k], lows[k + 1]) for k in range(max(0, len(lows) - max_sw), len(lows) - 1)]
        for (i1, s1), (i2, s2) in low_pairs:
            r1, r2 = rs[i1], rs[i2]
            if s2.price > s1.price and r1 is not None and r2 is not None and r2 < r1 and r2 < 50:
                out.append(Detection(
                    strategy_id=self.strategy_id, algo_version=ALGO_VERSION, symbol=ctx.symbol,
                    interval=ctx.interval, direction="bullish", anchor_time=_ts(ctx, i2),
                    levels={"swing_low_1": s1.price, "swing_low_2": s2.price,
                            "level": s2.price, "stop": s2.price - 1.5 * (_atr_at(ctx, i2))},
                    evidence=[f"Hidden bullish div: price HL {s1.price:.2f}→{s2.price:.2f}, RSI {r1:.1f}→{r2:.1f}"],
                    params={},
                ))
        high_pairs = [(highs[k], highs[k + 1]) for k in range(max(0, len(highs) - max_sw), len(highs) - 1)]
        for (i1, s1), (i2, s2) in high_pairs:
            r1, r2 = rs[i1], rs[i2]
            if s2.price < s1.price and r1 is not None and r2 is not None and r2 > r1 and r2 > 50:
                out.append(Detection(
                    strategy_id=self.strategy_id, algo_version=ALGO_VERSION, symbol=ctx.symbol,
                    interval=ctx.interval, direction="bearish", anchor_time=_ts(ctx, i2),
                    levels={"swing_high_1": s1.price, "swing_high_2": s2.price,
                            "level": s2.price, "stop": s2.price + 1.5 * (_atr_at(ctx, i2))},
                    evidence=[f"Hidden bearish div: price LH {s1.price:.2f}→{s2.price:.2f}, RSI {r1:.1f}→{r2:.1f}"],
                    params={},
                ))
        seen: set[datetime] = set()
        return [d for d in out if not (d.anchor_time in seen or seen.add(d.anchor_time))][-20:]


class TrendExhaustionStrategy(Strategy):
    strategy_id = "quant_exhaustion"
    name = "Trend Exhaustion"
    description = (
        "Extended directional move (≥ N consecutive higher closes) with RSI at an extreme "
        "(≥70 / ≤30) and decelerating momentum (last bar's gain < half the move's average "
        "bar gain) — warns the move is tiring. Verdict points AGAINST the exhausted move."
    )
    default_params = {"min_run": 6, "rsi_hi": 70, "rsi_lo": 30}

    def detect(self, ctx: CandleContext) -> list[Detection]:
        rs = rsi_series(ctx.closes, 14)
        out: list[Detection] = []
        min_run = int(self.default_params["min_run"])
        for i in range(min_run + 1, len(ctx.closes) - 1):
            r = rs[i]
            if r is None:
                continue
            run_up = all(ctx.closes[k] > ctx.closes[k - 1] for k in range(i - min_run + 1, i + 1))
            run_down = all(ctx.closes[k] < ctx.closes[k - 1] for k in range(i - min_run + 1, i + 1))
            if not (run_up or run_down):
                continue
            move = ctx.closes[i] - ctx.closes[i - min_run]
            avg_bar = abs(move) / min_run
            last_bar = abs(ctx.closes[i] - ctx.closes[i - 1])
            if run_up and r >= float(self.default_params["rsi_hi"]) and last_bar < 0.5 * avg_bar:
                out.append(Detection(
                    strategy_id=self.strategy_id, algo_version=ALGO_VERSION, symbol=ctx.symbol,
                    interval=ctx.interval, direction="bearish", anchor_time=_ts(ctx, i),
                    levels={"run_high": ctx.closes[i], "level": ctx.closes[i],
                            "stop": ctx.closes[i] + 1.2 * _atr_at(ctx, i)},
                    evidence=[f"Uptrend exhaustion: {min_run} higher closes, RSI {r:.1f}, momentum halved"],
                    params={},
                ))
            if run_down and r <= float(self.default_params["rsi_lo"]) and last_bar < 0.5 * avg_bar:
                out.append(Detection(
                    strategy_id=self.strategy_id, algo_version=ALGO_VERSION, symbol=ctx.symbol,
                    interval=ctx.interval, direction="bullish", anchor_time=_ts(ctx, i),
                    levels={"run_low": ctx.closes[i], "level": ctx.closes[i],
                            "stop": ctx.closes[i] - 1.2 * _atr_at(ctx, i)},
                    evidence=[f"Downtrend exhaustion: {min_run} lower closes, RSI {r:.1f}, momentum halved"],
                    params={},
                ))
        seen: set[datetime] = set()
        return [d for d in out if not (d.anchor_time in seen or seen.add(d.anchor_time))][-20:]


class VolatilityRegimeStrategy(Strategy):
    strategy_id = "quant_vol_regime"
    name = "Volatility Expansion / Contraction"
    description = (
        "Bollinger-band width squeeze (width at its lowest in lookback) flags contraction — "
        "expect an expansion break; a width surge from low base flags expansion already underway. "
        "Direction-neutral context signal (verdict NEUTRAL with actionable context)."
    )
    default_params = {"bb_period": 20, "lookback": 100, "squeeze_pct": 10}

    def detect(self, ctx: CandleContext) -> list[Detection]:
        n = int(self.default_params["bb_period"])
        look = int(self.default_params["lookback"])
        squeeze_pct = float(self.default_params["squeeze_pct"])
        widths: list[tuple[datetime, float]] = []
        for i in range(n, len(ctx.closes)):
            w = ctx.closes[i - n: i + 1]
            mean = sum(w) / n
            var = sum((x - mean) ** 2 for x in w) / n
            sd = var ** 0.5
            widths.append((_ts(ctx, i), 4 * sd / mean * 100 if mean else 0.0))
        if len(widths) < look:
            return []
        out: list[Detection] = []
        vals = [w for _, w in widths[-look:]]
        last_t, last_w = widths[-1]
        rank = sum(1 for v in vals if v < last_w) / len(vals)
        if rank <= squeeze_pct / 100:
            out.append(Detection(
                strategy_id=self.strategy_id, algo_version=ALGO_VERSION, symbol=ctx.symbol,
                interval=ctx.interval, direction="neutral", anchor_time=last_t,
                levels={"bb_width_pct": round(last_w, 3), "level": ctx.closes[-1]},
                evidence=[f"Volatility contraction: BB width {last_w:.2f}% at {rank * 100:.0f}th percentile of {look} bars — expansion break likely"],
                params={},
            ))
        elif rank >= 0.85 and vals[-1] > vals[-10] * 1.5:
            out.append(Detection(
                strategy_id=self.strategy_id, algo_version=ALGO_VERSION, symbol=ctx.symbol,
                interval=ctx.interval, direction="neutral", anchor_time=last_t,
                levels={"bb_width_pct": round(last_w, 3), "level": ctx.closes[-1]},
                evidence=[f"Volatility expansion: BB width surged to {last_w:.2f}% (from {vals[-10]:.2f}%) — trend-continuation moves favored"],
                params={},
            ))
        return out[-10:]
