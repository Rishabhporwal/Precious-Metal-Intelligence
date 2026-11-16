"""SMC core strategies (P0). All thresholds ATR-normalized where sensible."""

from __future__ import annotations

from strategies.base import ALGO_VERSION, CandleContext, Detection, Strategy


class LiquiditySweepStrategy(Strategy):
    strategy_id = "smc_liquidity_sweep"
    name = "Liquidity Sweep"
    description = (
        "Wick through a liquidity level (prior swing, EQH/EQL, PDH/PDL) followed by a "
        "close back inside within N bars (reclaim). Direction = side of the reclaimed level."
    )
    default_params = {"lookback_levels": 40, "reclaim_bars": 3, "min_wick_atr": 0.05}

    def detect(self, ctx: CandleContext) -> list[Detection]:
        p = {**self.default_params, **ctx.params}
        n = len(ctx.closes)
        atrv = ctx.atr_at(n - 1)
        if atrv is None or n < 10:
            return []
        # candidate liquidity levels: confirmed swings + PDH/PDL + PWH/PWL
        levels: list[tuple[str, float, str]] = []  # (label, price, side)
        for s in ctx.swings:
            if s.confirmed_index <= n - 1 - 1:  # swing fully confirmed before the last bar
                levels.append((f"swing_{s.kind}_{s.index}", s.price, s.kind))
        if ctx.pdh is not None:
            levels.append(("PDH", ctx.pdh, "high"))
        if ctx.pdl is not None:
            levels.append(("PDL", ctx.pdl, "low"))
        if ctx.pwh is not None:
            levels.append(("PWH", ctx.pwh, "high"))
        if ctx.pwl is not None:
            levels.append(("PWL", ctx.pwl, "low"))

        out: list[Detection] = []
        seen: set[tuple[str, int]] = set()
        # scan the recent window for pierce + reclaim (within reclaim_bars) patterns
        for i in range(max(1, n - p["lookback_levels"]), n):
            for label, price, side in levels:
                hi, lo = ctx.highs[i], ctx.lows[i]
                if side == "low" and lo < price:
                    # find the reclaim close within reclaim_bars
                    for j in range(i, min(n, i + p["reclaim_bars"] + 1)):
                        if ctx.closes[j] > price:
                            key = (label, i)
                            if key in seen:
                                break
                            seen.add(key)
                            wick = price - lo
                            if wick >= p["min_wick_atr"] * atrv:
                                out.append(
                                    Detection(
                                        strategy_id=self.strategy_id,
                                        algo_version=ALGO_VERSION,
                                        symbol=ctx.symbol,
                                        interval=ctx.interval,
                                        direction="bullish",
                                        anchor_time=ctx.times[j],
                                        levels={"level": price, "sweep_low": lo, "atr": atrv},
                                        evidence=[
                                            f"wicked below {label} ({price:.4f}) to {lo:.4f} @ bar {i}",
                                            f"reclaimed: closed above at {ctx.closes[j]:.4f} (bar {j})",
                                        ],
                                        params=p,
                                    )
                                )
                            break
                        if ctx.closes[j] < price - 2 * atrv:
                            break  # deep continuation — not a sweep, stop looking
                elif side == "high" and hi > price:
                    for j in range(i, min(n, i + p["reclaim_bars"] + 1)):
                        if ctx.closes[j] < price:
                            key = (label, i)
                            if key in seen:
                                break
                            seen.add(key)
                            wick = hi - price
                            if wick >= p["min_wick_atr"] * atrv:
                                out.append(
                                    Detection(
                                        strategy_id=self.strategy_id,
                                        algo_version=ALGO_VERSION,
                                        symbol=ctx.symbol,
                                        interval=ctx.interval,
                                        direction="bearish",
                                        anchor_time=ctx.times[j],
                                        levels={"level": price, "sweep_high": hi, "atr": atrv},
                                        evidence=[
                                            f"wicked above {label} ({price:.4f}) to {hi:.4f} @ bar {i}",
                                            f"reclaimed: closed below at {ctx.closes[j]:.4f} (bar {j})",
                                        ],
                                        params=p,
                                    )
                                )
                            break
                        if ctx.closes[j] > price + 2 * atrv:
                            break
        return out[-10:]


class FairValueGapStrategy(Strategy):
    strategy_id = "smc_fvg"
    name = "Fair Value Gap (FVG)"
    description = (
        "Three-candle imbalance: bullish FVG when low[i] > high[i-2]; bearish when "
        "high[i] < low[i-2]. Gap status tracked until filled (mitigated)."
    )
    default_params = {"min_gap_atr": 0.1, "open_window": 20}

    def detect(self, ctx: CandleContext) -> list[Detection]:
        p = {**self.default_params, **ctx.params}
        n = len(ctx.closes)
        out: list[Detection] = []
        for i in range(2, n):
            atrv = ctx.atr_at(i)
            if atrv is None:
                continue
            h_prev2, l_now, l_prev2, h_now = ctx.highs[i - 2], ctx.lows[i], ctx.lows[i - 2], ctx.highs[i]
            gap_up = l_now - h_prev2
            gap_down = l_prev2 - h_now
            if gap_up >= p["min_gap_atr"] * atrv:
                filled = any(ctx.lows[j] <= h_prev2 for j in range(i + 1, min(n, i + p["open_window"] + 1)))
                out.append(
                    Detection(
                        strategy_id=self.strategy_id,
                        algo_version=ALGO_VERSION,
                        symbol=ctx.symbol,
                        interval=ctx.interval,
                        direction="bullish",
                        anchor_time=ctx.times[i],
                        levels={"gap_high": l_now, "gap_low": h_prev2, "atr": atrv},
                        evidence=[
                            f"bullish FVG: low {l_now:.4f} > high[i-2] {h_prev2:.4f} (gap {gap_up:.4f})",
                            "filled" if filled else "unfilled (open gap)",
                        ],
                        params=p,
                        status="consumed" if filled else "active",
                    )
                )
            if gap_down >= p["min_gap_atr"] * atrv:
                filled = any(ctx.highs[j] >= l_prev2 for j in range(i + 1, min(n, i + p["open_window"] + 1)))
                out.append(
                    Detection(
                        strategy_id=self.strategy_id,
                        algo_version=ALGO_VERSION,
                        symbol=ctx.symbol,
                        interval=ctx.interval,
                        direction="bearish",
                        anchor_time=ctx.times[i],
                        levels={"gap_high": l_prev2, "gap_low": h_now, "atr": atrv},
                        evidence=[
                            f"bearish FVG: high {h_now:.4f} < low[i-2] {l_prev2:.4f} (gap {gap_down:.4f})",
                            "filled" if filled else "unfilled (open gap)",
                        ],
                        params=p,
                        status="consumed" if filled else "active",
                    )
                )
        # keep the most recent few only
        return out[-12:]


class OrderBlockStrategy(Strategy):
    strategy_id = "smc_order_block"
    name = "Order Block"
    description = (
        "Last opposite-direction candle before a displacement leg that breaks structure. "
        "Zone = candle body extremes; tracked until mitigated."
    )
    default_params = {"displacement_atr": 1.2, "confirm_bars": 5, "max_age_bars": 100}

    def detect(self, ctx: CandleContext) -> list[Detection]:
        p = {**self.default_params, **ctx.params}
        n = len(ctx.closes)
        out: list[Detection] = []
        for ev in ctx.events:
            if ev.kind not in ("bos_bullish", "bos_bearish", "choch_bullish", "choch_bearish"):
                continue
            i = ev.index
            atrv = ctx.atr_at(i)
            if atrv is None:
                continue
            bullish_ev = ev.kind in ("bos_bullish", "choch_bullish")
            # search back for the last opposite candle within displacement window
            zone_i = None
            for j in range(i - 1, max(-1, i - p["confirm_bars"] - 1), -1):
                if j < 0:
                    break
                bull_candle = ctx.closes[j] > ctx.opens[j]
                if bullish_ev and not bull_candle:
                    zone_i = j
                    break
                if not bullish_ev and bull_candle:
                    zone_i = j
                    break
            if zone_i is None:
                continue
            # displacement leg size
            move = abs(ctx.closes[i] - ctx.opens[max(0, i - p["confirm_bars"])])
            if move < p["displacement_atr"] * atrv:
                continue
            mitigated = False
            zone_high = float(ctx.highs[zone_i])
            zone_low = float(ctx.lows[zone_i])
            for j in range(i + 1, min(n, i + p["max_age_bars"])):
                if bullish_ev and ctx.lows[j] <= zone_high:
                    mitigated = True
                    break
                if not bullish_ev and ctx.highs[j] >= zone_low:
                    mitigated = True
                    break
            direction = "bullish" if bullish_ev else "bearish"
            out.append(
                Detection(
                    strategy_id=self.strategy_id,
                    algo_version=ALGO_VERSION,
                    symbol=ctx.symbol,
                    interval=ctx.interval,
                    direction=direction,
                    anchor_time=ctx.times[zone_i],
                    levels={
                        "zone_high": zone_high,
                        "zone_low": zone_low,
                        "structure_level": ev.level,
                        "atr": atrv,
                    },
                    evidence=[
                        f"{'bullish' if bullish_ev else 'bearish'} structure event @ {ctx.times[i].isoformat()}",
                        f"opposite candle zone {zone_low:.4f}-{zone_high:.4f} (bar {zone_i})",
                        f"displacement {move:.4f} ({move / atrv:.2f} ATR)",
                        "mitigated" if mitigated else "unmitigated",
                    ],
                    params=p,
                    status="consumed" if mitigated else "active",
                )
            )
        return out[-10:]

