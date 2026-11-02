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


class EqualHighsLowsStrategy(Strategy):
    strategy_id = "smc_eqh_eql"
    name = "Equal Highs / Equal Lows"
    description = (
        "Two or more confirmed swing highs (lows) within tolerance form a liquidity pool "
        "(EQH / EQL) — recorded as a resting-liquidity level, not a directional signal."
    )
    default_params = {"tolerance_atr": 0.15, "max_age_bars": 500}

    def detect(self, ctx: CandleContext) -> list[Detection]:
        p = {**self.default_params, **ctx.params}
        n = len(ctx.closes)
        atrv = ctx.atr_at(n - 1)
        if atrv is None:
            return []
        tol = p["tolerance_atr"] * atrv
        highs = [s for s in ctx.swings if s.kind == "high"]
        lows = [s for s in ctx.swings if s.kind == "low"]
        out: list[Detection] = []

        def pools(group, kind: str) -> None:
            for a in range(len(group)):
                for b in range(a + 1, len(group)):
                    s1, s2 = group[a], group[b]
                    if s2.index - s1.index > p["max_age_bars"]:
                        continue
                    if abs(s1.price - s2.price) <= tol and s2.confirmed_index <= n - 1:
                        pool_price = (s1.price + s2.price) / 2
                        out.append(
                            Detection(
                                strategy_id=self.strategy_id,
                                algo_version=ALGO_VERSION,
                                symbol=ctx.symbol,
                                interval=ctx.interval,
                                direction="neutral",
                                anchor_time=ctx.times[s2.confirmed_index],
                                levels={"pool": pool_price, "level_a": s1.price, "level_b": s2.price},
                                evidence=[
                                    f"{kind} swing {s1.price:.4f} @ {s1.index}",
                                    f"{kind} swing {s2.price:.4f} @ {s2.index}",
                                    f"tolerance {tol:.4f} (0.15 ATR default)",
                                ],
                                params=p,
                            )
                        )
                    break  # only nearest pair per anchor (avoid O(n^2) spam)

        pools(highs, "EQH")
        pools(lows, "EQL")
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


class BreakerBlockStrategy(Strategy):
    strategy_id = "smc_breaker"
    name = "Breaker Block"
    description = (
        "An order block whose direction failed (price closed through it) — flips to an "
        "opposite-direction zone once violated."
    )
    default_params = {"max_age_bars": 100}

    def detect(self, ctx: CandleContext) -> list[Detection]:
        p = {**self.default_params, **ctx.params}
        ob = OrderBlockStrategy()
        ob.default_params = {"displacement_atr": 1.2, "confirm_bars": 5, "max_age_bars": p["max_age_bars"]}
        obs = ob.detect(ctx)
        n = len(ctx.closes)
        out: list[Detection] = []
        for d in obs:
            if d.status != "active":
                continue
            zone_high = d.levels["zone_high"]
            zone_low = d.levels["zone_low"]
            anchor_idx = next(
                (i for i, t in enumerate(ctx.times) if t == d.anchor_time), None
            )
            if anchor_idx is None:
                continue
            violated_up = any(ctx.closes[j] > zone_high for j in range(anchor_idx + 1, n))
            violated_down = any(ctx.closes[j] < zone_low for j in range(anchor_idx + 1, n))
            if d.direction == "bearish" and violated_up:
                out.append(
                    Detection(
                        strategy_id=self.strategy_id,
                        algo_version=ALGO_VERSION,
                        symbol=ctx.symbol,
                        interval=ctx.interval,
                        direction="bullish",
                        anchor_time=ctx.times[-1],
                        levels={"zone_high": zone_high, "zone_low": zone_low},
                        evidence=[f"bearish OB {zone_low:.4f}-{zone_high:.4f} violated upward → breaker"],
                        params=p,
                    )
                )
            elif d.direction == "bullish" and violated_down:
                out.append(
                    Detection(
                        strategy_id=self.strategy_id,
                        algo_version=ALGO_VERSION,
                        symbol=ctx.symbol,
                        interval=ctx.interval,
                        direction="bearish",
                        anchor_time=ctx.times[-1],
                        levels={"zone_high": zone_high, "zone_low": zone_low},
                        evidence=[f"bullish OB {zone_low:.4f}-{zone_high:.4f} violated downward → breaker"],
                        params=p,
                    )
                )
        return out[-6:]


class DisplacementStrategy(Strategy):
    strategy_id = "smc_displacement"
    name = "Displacement"
    description = (
        "Large directional candle/body (>= k ATR) — momentum signature often accompanying "
        "structure breaks and FVG creation."
    )
    default_params = {"body_atr": 1.5, "lookback": 30}

    def detect(self, ctx: CandleContext) -> list[Detection]:
        p = {**self.default_params, **ctx.params}
        n = len(ctx.closes)
        out: list[Detection] = []
        for i in range(max(1, n - p["lookback"]), n):
            atrv = ctx.atr_at(i)
            if atrv is None:
                continue
            body = abs(ctx.closes[i] - ctx.opens[i])
            if body >= p["body_atr"] * atrv:
                direction = "bullish" if ctx.closes[i] > ctx.opens[i] else "bearish"
                out.append(
                    Detection(
                        strategy_id=self.strategy_id,
                        algo_version=ALGO_VERSION,
                        symbol=ctx.symbol,
                        interval=ctx.interval,
                        direction=direction,
                        anchor_time=ctx.times[i],
                        levels={"body": body, "atr": atrv},
                        evidence=[f"body {body:.4f} = {body / atrv:.2f} ATR ({direction})"],
                        params=p,
                    )
                )
        return out


class PremiumDiscountStrategy(Strategy):
    strategy_id = "smc_premium_discount"
    name = "Premium / Discount"
    description = (
        "Dealing range from the latest confirmed swing high/low pair; equilibrium at 50%. "
        "Classifies current price as premium/discount/equilibrium."
    )
    default_params = {}

    def detect(self, ctx: CandleContext) -> list[Detection]:
        n = len(ctx.closes)
        if n == 0:
            return []
        highs = [s for s in ctx.swings if s.kind == "high"]
        lows = [s for s in ctx.swings if s.kind == "low"]
        if not highs or not lows:
            return []
        range_high = max(s.price for s in highs[-6:])
        range_low = min(s.price for s in lows[-6:])
        if range_high <= range_low:
            return []
        eq = (range_high + range_low) / 2
        price = ctx.closes[-1]
        if price > eq * 1.005:
            zone = "premium"
            direction = "bearish"
        elif price < eq * 0.995:
            zone = "discount"
            direction = "bullish"
        else:
            zone = "equilibrium"
            direction = "neutral"
        return [
            Detection(
                strategy_id=self.strategy_id,
                algo_version=ALGO_VERSION,
                symbol=ctx.symbol,
                interval=ctx.interval,
                direction=direction,
                anchor_time=ctx.times[-1],
                levels={"range_high": range_high, "range_low": range_low, "equilibrium": eq},
                evidence=[
                    f"price {price:.4f} in {zone} of dealing range {range_low:.4f}-{range_high:.4f}",
                    f"equilibrium {eq:.4f}",
                ],
                params={},
            )
        ]
