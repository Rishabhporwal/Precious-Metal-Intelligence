"""Strategy framework core types.

Every strategy is deterministic, consumes only confirmed (closed) candles and
already-confirmed structure (swings need their confirmation bars), and declares
an algorithm version. A detection is NOT a trade recommendation — confluence,
confirmation and risk validation are separate gates (Phases 4/8).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar

from indicators import atr as atr_fn
from indicators import structure as st
from indicators.structure import StructureEvent, Swing

ALGO_VERSION = "smc-1.0.0"


@dataclass(frozen=True)
class CandleContext:
    """Immutable view over stored candles for ONE instrument + interval."""

    symbol: str
    interval: str
    times: list[datetime]
    opens: list[float]
    highs: list[float]
    lows: list[float]
    closes: list[float]
    swings: list[Swing]
    events: list[StructureEvent]
    atr: list[float | None]
    pdh: float | None = None
    pdl: float | None = None
    pwh: float | None = None
    pwl: float | None = None
    sessions: dict[str, dict] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)

    def atr_at(self, index: int, fallback_periods: int = 14) -> float | None:
        """ATR at index, walking back to the last defined value (no future reads)."""
        for i in range(min(index, len(self.atr) - 1), -1, -1):
            v = self.atr[i]
            if v is not None:
                return v
        return None


@dataclass(frozen=True)
class Detection:
    """One strategy detection record (append-only, persisted)."""

    strategy_id: str
    algo_version: str
    symbol: str
    interval: str
    direction: str  # bullish | bearish | neutral
    anchor_time: datetime  # market time of the anchoring candle
    levels: dict[str, float | None]  # named numeric levels (zones, entry refs)
    evidence: list[str]
    params: dict[str, Any]
    status: str = "active"  # active | consumed | expired


class Strategy(ABC):
    strategy_id: str
    name: str
    description: str
    default_params: ClassVar[dict[str, Any]] = {}

    @abstractmethod
    def detect(self, ctx: CandleContext) -> list[Detection]:
        ...


def build_context(
    symbol: str,
    interval: str,
    rows: list[dict],
    daily: list[dict],
    hourly: list[dict],
    params: dict[str, Any] | None = None,
) -> CandleContext:
    """Build the CandleContext from stored candle rows (already ascending)."""
    highs = [float(r["high"]) for r in rows]
    lows = [float(r["low"]) for r in rows]
    closes = [float(r["close"]) for r in rows]
    opens = [float(r["open"]) for r in rows]
    times = [r["market_ts"] if isinstance(r["market_ts"], datetime) else datetime.fromisoformat(str(r["market_ts"])) for r in rows]
    swings = st.detect_swings(highs, lows)
    events = st.detect_structure_events(closes, swings)
    atr_series = atr_fn(highs, lows, closes, 14)
    pdh, pdl = st.prev_day_high_low(daily)
    pwh, pwl = st.prev_week_high_low(daily)
    sessions = st.session_ranges(hourly)
    return CandleContext(
        symbol=symbol,
        interval=interval,
        times=times,
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        swings=swings,
        events=events,
        atr=atr_series,
        pdh=pdh,
        pdl=pdl,
        pwh=pwh,
        pwl=pwl,
        sessions=sessions,
        params=params or {},
    )
