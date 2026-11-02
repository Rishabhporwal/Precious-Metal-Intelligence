"""SMT divergence between two instruments (Gold/Silver by default).

Real divergence: correlated instruments make simultaneous swing highs/lows and
one fails to exceed the other's corresponding extreme. Runs purely on stored
candles for both instruments — no fabrication. With silver on the COMEX SI
proxy, results are labeled as gold-vs-silver-futures.
"""

from __future__ import annotations

from datetime import datetime

from strategies.base import ALGO_VERSION, CandleContext, Detection, Strategy


class SMTDivergenceStrategy(Strategy):
    strategy_id = "cross_market_smt"
    name = "SMT Divergence (Gold vs Silver)"
    description = (
        "Compares confirmed swing extremes of two correlated instruments within a time "
        "window. Gold makes a higher high while the counterpart fails (or vice versa) — "
        "smart-money divergence tell. Direction applies to gold."
    )
    default_params = {"window_bars": 12, "counterpart_symbol": "XAGUSD"}

    def detect(self, ctx: CandleContext) -> list[Detection]:
        # counterpart candles are injected via params by the engine
        counterpart = ctx.params.get("counterpart_candles")
        p = {**self.default_params, **{k: v for k, v in ctx.params.items() if k != "counterpart_candles"}}
        if not counterpart:
            return []
        c_highs = [float(r["high"]) for r in counterpart]
        c_lows = [float(r["low"]) for r in counterpart]
        c_times = [
            r["market_ts"] if isinstance(r["market_ts"], datetime) else datetime.fromisoformat(str(r["market_ts"]))
            for r in counterpart
        ]
        c_swings = __import__("indicators").structure.detect_swings(c_highs, c_lows)

        out: list[Detection] = []
        gold_highs = [s for s in ctx.swings if s.kind == "high"]
        gold_lows = [s for s in ctx.swings if s.kind == "low"]
        c_high_swings = [s for s in c_swings if s.kind == "high"]
        c_low_swings = [s for s in c_swings if s.kind == "low"]

        def counterpart_index_near(t: datetime, window_s: int = 3600 * 24) -> int | None:
            best = None
            for i, ct in enumerate(c_times):
                dt = abs((ct - t).total_seconds())
                if dt <= window_s and (best is None or dt < abs((c_times[best] - t).total_seconds())):
                    best = i
            return best

        # bearish SMT: gold HH, counterpart fails to make HH at the same time
        for s in gold_highs[-6:]:
            j = counterpart_index_near(ctx.times[s.confirmed_index])
            if j is None:
                continue
            prev_c = [x for x in c_high_swings if x.index < j]
            prev_g = [x for x in gold_highs if x.index < s.index and x.price < s.price]
            if not prev_c or not prev_g:
                continue
            gold_made_hh = s.price > prev_g[-1].price
            counter_failed = c_highs[j] < max(c_highs[: j + 1][:-1]) if j > 0 else False
            if gold_made_hh and counter_failed:
                out.append(
                    Detection(
                        strategy_id=self.strategy_id,
                        algo_version=ALGO_VERSION,
                        symbol=ctx.symbol,
                        interval=ctx.interval,
                        direction="bearish",
                        anchor_time=ctx.times[s.confirmed_index],
                        levels={"gold_high": s.price, "counterpart_high": c_highs[j]},
                        evidence=[
                            f"gold HH {s.price:.4f} @ {ctx.times[s.confirmed_index].isoformat()}",
                            f"counterpart failed to exceed {c_highs[j]:.4f}",
                        ],
                        params=p,
                    )
                )

        # bullish SMT: gold LL, counterpart holds a higher low
        for s in gold_lows[-6:]:
            j = counterpart_index_near(ctx.times[s.confirmed_index])
            if j is None:
                continue
            prev_c_lows = [x for x in c_low_swings if x.index < j]
            prev_g_lows = [x for x in gold_lows if x.index < s.index and x.price > s.price]
            if not prev_c_lows or not prev_g_lows:
                continue
            gold_made_ll = s.price < prev_g_lows[-1].price
            counter_held = c_lows[j] > min(c_lows[: j + 1][:-1]) if j > 0 else False
            if gold_made_ll and counter_held:
                out.append(
                    Detection(
                        strategy_id=self.strategy_id,
                        algo_version=ALGO_VERSION,
                        symbol=ctx.symbol,
                        interval=ctx.interval,
                        direction="bullish",
                        anchor_time=ctx.times[s.confirmed_index],
                        levels={"gold_low": s.price, "counterpart_low": c_lows[j]},
                        evidence=[
                            f"gold LL {s.price:.4f} @ {ctx.times[s.confirmed_index].isoformat()}",
                            f"counterpart held higher low {c_lows[j]:.4f}",
                        ],
                        params=p,
                    )
                )
        return out[-6:]
