"""Wyckoff P0 events: Spring and Upthrust (basic event detection, no phase claims)."""

from __future__ import annotations

from strategies.base import ALGO_VERSION, CandleContext, Detection, Strategy


class WyckoffSpringStrategy(Strategy):
    strategy_id = "wyckoff_spring"
    name = "Wyckoff Spring"
    description = (
        "After a consolidation (N bars with range inside a support band), a break below "
        "support that is reclaimed within M bars — a spring. Price-only; no volume or "
        "phase claims."
    )
    default_params = {"consolidation_bars": 20, "range_atr": 2.0, "reclaim_bars": 3}

    def detect(self, ctx: CandleContext) -> list[Detection]:
        p = {**self.default_params, **ctx.params}
        n = len(ctx.closes)
        out: list[Detection] = []
        i = p["consolidation_bars"]
        while i < n - p["reclaim_bars"] - 1:
            atrv = ctx.atr_at(i)
            if atrv is None:
                i += 1
                continue
            window_lo = min(ctx.lows[i - p["consolidation_bars"] : i])
            window_hi = max(ctx.highs[i - p["consolidation_bars"] : i])
            in_range = (window_hi - window_lo) <= p["range_atr"] * atrv
            if in_range:
                support = window_lo
                # spring: break below support then reclaim within M bars
                for j in range(i, min(n, i + p["reclaim_bars"] + 1)):
                    if ctx.lows[j] < support and ctx.closes[j] > support:
                        out.append(
                            Detection(
                                strategy_id=self.strategy_id,
                                algo_version=ALGO_VERSION,
                                symbol=ctx.symbol,
                                interval=ctx.interval,
                                direction="bullish",
                                anchor_time=ctx.times[j],
                                levels={"support": support, "spring_low": ctx.lows[j], "range_high": window_hi},
                                evidence=[
                                    f"consolidation {p['consolidation_bars']} bars ({window_lo:.4f}-{window_hi:.4f})",
                                    f"break below support {support:.4f} at bar {j} (low {ctx.lows[j]:.4f})",
                                    f"reclaimed close {ctx.closes[j]:.4f}",
                                ],
                                params=p,
                            )
                        )
                        i = j + 1
                        break
                else:
                    i += 1
            else:
                i += 1
        return out[-6:]


class WyckoffUpthrustStrategy(Strategy):
    strategy_id = "wyckoff_upthrust"
    name = "Wyckoff Upthrust"
    description = (
        "After a consolidation, a push above resistance that closes back below within M "
        "bars — an upthrust (UT/UTAD signature). Price-only; no phase claims."
    )
    default_params = {"consolidation_bars": 20, "range_atr": 2.0, "reclaim_bars": 3}

    def detect(self, ctx: CandleContext) -> list[Detection]:
        p = {**self.default_params, **ctx.params}
        n = len(ctx.closes)
        out: list[Detection] = []
        i = p["consolidation_bars"]
        while i < n - p["reclaim_bars"] - 1:
            atrv = ctx.atr_at(i)
            if atrv is None:
                i += 1
                continue
            window_lo = min(ctx.lows[i - p["consolidation_bars"] : i])
            window_hi = max(ctx.highs[i - p["consolidation_bars"] : i])
            in_range = (window_hi - window_lo) <= p["range_atr"] * atrv
            if in_range:
                resistance = window_hi
                for j in range(i, min(n, i + p["reclaim_bars"] + 1)):
                    if ctx.highs[j] > resistance and ctx.closes[j] < resistance:
                        out.append(
                            Detection(
                                strategy_id=self.strategy_id,
                                algo_version=ALGO_VERSION,
                                symbol=ctx.symbol,
                                interval=ctx.interval,
                                direction="bearish",
                                anchor_time=ctx.times[j],
                                levels={"resistance": resistance, "upthrust_high": ctx.highs[j], "range_low": window_lo},
                                evidence=[
                                    f"consolidation {p['consolidation_bars']} bars ({window_lo:.4f}-{window_hi:.4f})",
                                    f"push above resistance {resistance:.4f} at bar {j} (high {ctx.highs[j]:.4f})",
                                    f"failed close {ctx.closes[j]:.4f}",
                                ],
                                params=p,
                            )
                        )
                        i = j + 1
                        break
                else:
                    i += 1
            else:
                i += 1
        return out[-6:]
