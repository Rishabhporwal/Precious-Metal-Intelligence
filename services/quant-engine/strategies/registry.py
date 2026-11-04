"""Strategy registry — single source of P0 strategy classes."""

from __future__ import annotations

from strategies.base import Strategy
from strategies.confluence import SweepMssFvgObComposite
from strategies.ict import (
    AsianRangeStrategy,
    FailedBreakoutStrategy,
    FibonacciOTEStrategy,
    MarketStructureShiftStrategy,
    PDLpDHStrategy,
)
from strategies.ict_p1 import (
    AmdPowerOfThreeStrategy,
    IctSilverBulletStrategy,
    JudasSwingStrategy,
    LiquidityVoidStrategy,
    SessionRangeBreakoutStrategy,
)
from strategies.momentum import (
    BreakoutRetestStrategy,
    EmaAlignmentStrategy,
    HigherHighsStrategy,
    MomentumExpansionStrategy,
    MultiTimeframeAlignmentStrategy,
    PullbackInTrendStrategy,
    RangeBreakoutStrategy,
    TrendContinuationStrategy,
)
from strategies.quant_strategies import (
    HiddenDivergenceStrategy,
    TrendExhaustionStrategy,
    VolatilityRegimeStrategy,
    WyckoffSosSowStrategy,
)
from strategies.smc import (
    BreakerBlockStrategy,
    DisplacementStrategy,
    EqualHighsLowsStrategy,
    FairValueGapStrategy,
    LiquiditySweepStrategy,
    OrderBlockStrategy,
    PremiumDiscountStrategy,
)
from strategies.smt import SMTDivergenceStrategy
from strategies.wyckoff import WyckoffSpringStrategy, WyckoffUpthrustStrategy

ALL_STRATEGIES: list[type[Strategy]] = [
    LiquiditySweepStrategy,
    EqualHighsLowsStrategy,
    MarketStructureShiftStrategy,
    FairValueGapStrategy,
    OrderBlockStrategy,
    BreakerBlockStrategy,
    DisplacementStrategy,
    PremiumDiscountStrategy,
    PDLpDHStrategy,
    AsianRangeStrategy,
    FibonacciOTEStrategy,
    FailedBreakoutStrategy,
    WyckoffSpringStrategy,
    WyckoffUpthrustStrategy,
    SMTDivergenceStrategy,
    TrendContinuationStrategy,
    BreakoutRetestStrategy,
    RangeBreakoutStrategy,
    MomentumExpansionStrategy,
    EmaAlignmentStrategy,
    HigherHighsStrategy,
    PullbackInTrendStrategy,
    MultiTimeframeAlignmentStrategy,
    JudasSwingStrategy,
    AmdPowerOfThreeStrategy,
    IctSilverBulletStrategy,
    SessionRangeBreakoutStrategy,
    LiquidityVoidStrategy,
    WyckoffSosSowStrategy,
    HiddenDivergenceStrategy,
    TrendExhaustionStrategy,
    VolatilityRegimeStrategy,
    SweepMssFvgObComposite,
]

REGISTRY: dict[str, type[Strategy]] = {s.strategy_id: s for s in ALL_STRATEGIES}


def get_strategy(strategy_id: str) -> type[Strategy] | None:
    return REGISTRY.get(strategy_id)
