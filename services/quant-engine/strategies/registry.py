"""Strategy registry — the 7 production strategies (product decision: focus)."""

from __future__ import annotations

from strategies.base import Strategy
from strategies.ict import (
    FibonacciOTEStrategy,
    MarketStructureShiftStrategy,
)
from strategies.momentum import (
    EmaAlignmentStrategy,
)
from strategies.smc import (
    FairValueGapStrategy,
    LiquiditySweepStrategy,
    OrderBlockStrategy,
)
from strategies.wyckoff import (
    WyckoffSpringStrategy,
)

ALL_STRATEGIES: list[type[Strategy]] = [
    LiquiditySweepStrategy,  # smc_liquidity_sweep
    MarketStructureShiftStrategy,  # ict_mss
    FairValueGapStrategy,  # smc_fvg
    OrderBlockStrategy,  # smc_order_block
    FibonacciOTEStrategy,  # ict_fib_ote
    WyckoffSpringStrategy,  # wyckoff_spring
    EmaAlignmentStrategy,  # mom_ema_align
]

REGISTRY: dict[str, type[Strategy]] = {cls.strategy_id: cls for cls in ALL_STRATEGIES}
