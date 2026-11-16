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

