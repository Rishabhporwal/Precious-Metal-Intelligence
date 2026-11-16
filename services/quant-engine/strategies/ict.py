"""ICT / price-action P0 strategies."""

from __future__ import annotations

from strategies.base import ALGO_VERSION, CandleContext, Detection, Strategy


class MarketStructureShiftStrategy(Strategy):
    strategy_id = "ict_mss"
    name = "Market Structure Shift (MSS)"
    description = (
        "CHoCH confirmed with displacement: a change of character whose breaking candle "
        "body is >= k ATR. Stronger than a plain CHoCH."
    )
    default_params = {"displacement_atr": 1.0, "lookback": 60}

    def detect(self, ctx: CandleContext) -> list[Detection]:
        p = {**self.default_params, **ctx.params}
        n = len(ctx.closes)
        out: list[Detection] = []
        for ev in ctx.events:
            if not ev.kind.startswith("choch"):
                continue
            if ev.index < n - p["lookback"]:
                continue
            atrv = ctx.atr_at(ev.index)
            if atrv is None:
                continue
            body = abs(ctx.closes[ev.index] - ctx.opens[ev.index])
            if body < p["displacement_atr"] * atrv:
                continue
            direction = "bullish" if ev.kind == "choch_bullish" else "bearish"
            out.append(
                Detection(
                    strategy_id=self.strategy_id,
                    algo_version=ALGO_VERSION,
                    symbol=ctx.symbol,
                    interval=ctx.interval,
                    direction=direction,
                    anchor_time=ctx.times[ev.index],
                    levels={"broken_level": ev.level, "body": body, "atr": atrv},
                    evidence=[
                        f"{ev.kind} @ bar {ev.index}: level {ev.level:.4f}",
                        f"displacing body {body:.4f} = {body / atrv:.2f} ATR",
                    ],
                    params=p,
                )
            )
        return out[-6:]


class FibonacciOTEStrategy(Strategy):
    strategy_id = "ict_fib_ote"
    name = "Fibonacci / Optimal Trade Entry"
    description = (
        "On the latest confirmed impulse leg: bullish leg (swing low → swing high) leaves a "
        "bearish OTE sell zone at the 61.8–79% retracement; bearish leg leaves a bullish OTE "
        "buy zone. Reports the zone and whether price is inside it."
    )
    default_params = {"ote_low": 0.618, "ote_high": 0.79}

    def detect(self, ctx: CandleContext) -> list[Detection]:
        p = {**self.default_params, **ctx.params}
        highs = [s for s in ctx.swings if s.kind == "high"]
        lows = [s for s in ctx.swings if s.kind == "low"]
        if not highs or not lows:
            return []
        out: list[Detection] = []
        price = ctx.closes[-1]

        # Bearish OTE: bullish impulse (last swing low BEFORE last swing high)
        if lows[-1].index < highs[-1].confirmed_index:
            start, end = lows[-1].price, highs[-1].price
            span = end - start
            if span > 0:
                zone_hi = end - span * p["ote_low"]
                zone_lo = end - span * p["ote_high"]
                inside = zone_lo <= price <= zone_hi
                out.append(
                    Detection(
                        strategy_id=self.strategy_id,
                        algo_version=ALGO_VERSION,
                        symbol=ctx.symbol,
                        interval=ctx.interval,
                        direction="bearish",
                        anchor_time=ctx.times[highs[-1].confirmed_index],
                        levels={
                            "impulse_start": start,
                            "impulse_end": end,
                            "ote_high": zone_hi,
                            "ote_low": zone_lo,
                        },
                        evidence=[
                            f"bullish impulse {start:.4f} → {end:.4f}",
                            f"bearish OTE zone {zone_lo:.4f}-{zone_hi:.4f}",
                            "price inside OTE" if inside else f"price {price:.4f} outside OTE",
                        ],
                        params=p,
                        status="active" if inside else "expired",
                    )
                )

        # Bullish OTE: bearish impulse (last swing high BEFORE last swing low)
        if highs and lows and highs[-1].index < lows[-1].confirmed_index:
            start, end = highs[-1].price, lows[-1].price
            span = start - end
            if span > 0:
                zone_hi = end + span * p["ote_high"]
                zone_lo = end + span * p["ote_low"]
                inside = zone_lo <= price <= zone_hi
                out.append(
                    Detection(
                        strategy_id=self.strategy_id,
                        algo_version=ALGO_VERSION,
                        symbol=ctx.symbol,
                        interval=ctx.interval,
                        direction="bullish",
                        anchor_time=ctx.times[lows[-1].confirmed_index],
                        levels={
                            "impulse_start": start,
                            "impulse_end": end,
                            "ote_high": zone_hi,
                            "ote_low": zone_lo,
                        },
                        evidence=[
                            f"bearish impulse {start:.4f} → {end:.4f}",
                            f"bullish OTE zone {zone_lo:.4f}-{zone_hi:.4f}",
                            "price inside OTE" if inside else f"price {price:.4f} outside OTE",
                        ],
                        params=p,
                        status="active" if inside else "expired",
                    )
                )
        return out[-4:]

