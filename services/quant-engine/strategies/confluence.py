"""Confluence engine: combines independently-detected conditions into a
candidate scenario with satisfied/missing/conflicting conditions and Python-
computed levels. A scenario is NOT a trade recommendation."""

from __future__ import annotations

from dataclasses import dataclass, field

from strategies.base import ALGO_VERSION, CandleContext, Detection, Strategy
from strategies.ict import MarketStructureShiftStrategy
from strategies.smc import (
    DisplacementStrategy,
    FairValueGapStrategy,
    LiquiditySweepStrategy,
    OrderBlockStrategy,
)


@dataclass
class ConfluenceScenario:
    strategy_id: str
    direction: str
    anchor_time: object
    satisfied: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    conflicting: list[str] = field(default_factory=list)
    confirmation: list[str] = field(default_factory=list)
    invalidation: list[str] = field(default_factory=list)
    levels: dict = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    complete: bool = False


class SweepMssFvgObComposite(Strategy):
    strategy_id = "composite_sweep_mss_fvg_ob"
    name = "Composite: Sweep → MSS → Displacement → FVG → Order Block"
    description = (
        "First P0 composite. Bullish: sell-side liquidity swept (reclaim), then MSS/CHoCH "
        "with displacement, a bullish FVG forming, ideally overlapping an unmitigated "
        "bullish order block. Entry zone = FVG∩OB overlap; stop below sweep low; targets "
        "at R multiples. All levels are Python-computed from candle data."
    )
    default_params = {
        "window_bars": 12,          # max bars between sweep and MSS
        "target1_r": 1.0,
        "target2_r": 2.0,
        "target3_r": 3.0,
    }

    def detect(self, ctx: CandleContext) -> list[Detection]:
        p = {**self.default_params, **ctx.params}
        n = len(ctx.closes)

        sweeps = LiquiditySweepStrategy().detect(ctx)
        msss = MarketStructureShiftStrategy().detect(ctx)
        disps = DisplacementStrategy().detect(ctx)
        fvgs = FairValueGapStrategy().detect(ctx)
        obs = OrderBlockStrategy().detect(ctx)

        scenarios: list[ConfluenceScenario] = []
        for direction in ("bullish", "bearish"):
            dir_sweeps = [d for d in sweeps if d.direction == direction]
            dir_msss = [d for d in msss if d.direction == direction]
            dir_disps = [d for d in disps if d.direction == direction]
            dir_fvgs = [d for d in fvgs if d.direction == direction and d.status == "active"]
            dir_obs = [d for d in obs if d.direction == direction and d.status == "active"]

            for sweep in dir_sweeps:
                anchor_idx = self._index_of(ctx, sweep.anchor_time)
                if anchor_idx is None:
                    continue
                window_end = min(n, anchor_idx + p["window_bars"] + 1)

                def within(d: Detection, _a: int = anchor_idx, _w: int = window_end) -> bool:
                    idx = self._index_of(ctx, d.anchor_time)
                    return idx is not None and _a <= idx <= _w

                s_mss = next((d for d in dir_msss if within(d)), None)
                s_disp = next((d for d in dir_disps if within(d)), None)
                s_fvg = next((d for d in dir_fvgs if within(d)), None)
                s_ob = next((d for d in dir_obs if within(d)), None)

                satisfied = [f"Liquidity sweep ({direction})"]
                missing: list[str] = []
                conflicting: list[str] = []
                if s_mss:
                    satisfied.append("MSS/CHoCH confirmed")
                else:
                    missing.append("MSS/CHoCH confirmation")
                if s_disp:
                    satisfied.append("Displacement")
                else:
                    missing.append("Displacement candle")
                if s_fvg:
                    satisfied.append("FVG formed (open)")
                else:
                    missing.append("FVG")

                # conflicting: opposite-direction signals inside the window
                opp = "bearish" if direction == "bullish" else "bullish"
                if any(self._within_idx(ctx, d.anchor_time, anchor_idx, window_end) for d in sweeps if d.direction == opp):
                    conflicting.append(f"opposite-direction sweep ({opp})")

                overlap = None
                if s_fvg and s_ob:
                    f_lo, f_hi = s_fvg.levels["gap_low"], s_fvg.levels["gap_high"]
                    o_lo, o_hi = s_ob.levels["zone_low"], s_ob.levels["zone_high"]
                    ov_lo, ov_hi = max(f_lo, o_lo), min(f_hi, o_hi)
                    if ov_lo < ov_hi:
                        overlap = {"overlap_low": ov_lo, "overlap_high": ov_hi}
                        satisfied.append("FVG ∩ Order Block overlap")

                entry = overlap or (
                    {"entry_low": s_fvg.levels["gap_low"], "entry_high": s_fvg.levels["gap_high"]}
                    if s_fvg
                    else None
                )
                stop = (
                    sweep.levels.get("sweep_low")
                    if direction == "bullish"
                    else sweep.levels.get("sweep_high")
                )
                targets: dict[str, float | None] = {}
                if entry and stop is not None:
                    entry_ref = entry["entry_low" if direction == "bullish" else "entry_high"] if overlap is None else (
                        entry["overlap_low" if direction == "bullish" else "overlap_high"]
                    )
                    risk = abs(entry_ref - stop)
                    if risk > 0:
                        sign = 1 if direction == "bullish" else -1
                        for k in ("target1_r", "target2_r", "target3_r"):
                            targets[f"target_{k.split('_')[0]}"] = entry_ref + sign * p[k] * risk
                    satisfied.append("entry/stop/targets computed")

                complete = not missing
                scenarios.append(
                    ConfluenceScenario(
                        strategy_id=self.strategy_id,
                        direction=direction,
                        anchor_time=sweep.anchor_time,
                        satisfied=satisfied,
                        missing=missing,
                        conflicting=conflicting,
                        confirmation=[
                            "close back above/below swept level",
                            "higher-timeframe bias check (Phase 6)",
                            "macro/news gate (Phase 5+)",
                        ],
                        invalidation=[
                            f"close {'below sweep low' if direction == 'bullish' else 'above sweep high'}"
                            + (f" ({stop:.4f})" if stop is not None else ""),
                            "FVG fully mitigated against direction",
                        ],
                        levels={
                            **(overlap or {}),
                            **(entry or {}),
                            "stop": stop,
                            **targets,
                            **(sweep.levels or {}),
                        },
                        evidence=[e for d in (sweep, s_mss, s_disp, s_fvg, s_ob) if d for e in d.evidence],
                        complete=complete,
                    )
                )

        # convert scenarios to detections (persist all candidates, flag completeness)
        out: list[Detection] = []
        for s in scenarios:
            out.append(
                Detection(
                    strategy_id=self.strategy_id,
                    algo_version=ALGO_VERSION,
                    symbol=ctx.symbol,
                    interval=ctx.interval,
                    direction=s.direction,
                    anchor_time=s.anchor_time,  # type: ignore[arg-type]
                    levels={k: v for k, v in s.levels.items() if isinstance(v, (int, float))},
                    evidence=(
                        [f"complete={s.complete}"]
                        + [f"✓ {c}" for c in s.satisfied]
                        + [f"✗ missing: {c}" for c in s.missing]
                        + [f"⚠ conflict: {c}" for c in s.conflicting]
                        + s.evidence[:6]
                    ),
                    params=p,
                    status="active" if s.complete else "expired",
                )
            )
        return out[-6:]

    @staticmethod
    def _index_of(ctx: CandleContext, t) -> int | None:
        for i, ct in enumerate(ctx.times):
            if ct == t:
                return i
        return None

    @classmethod
    def _within_idx(cls, ctx: CandleContext, t, lo: int, hi: int) -> bool:
        idx = cls._index_of(ctx, t)
        return idx is not None and lo <= idx <= hi
