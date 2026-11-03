"""Independent Strategy Verdict Engine (new spec §5).

Every registered strategy gets its own standing verdict, computed
deterministically from its persisted/derived detections + current price.

Standard verdict model (§5.1):
  BULLISH | BEARISH | NEUTRAL | NO_SIGNAL | WAITING_FOR_CONFIRMATION
  | INVALIDATED | INSUFFICIENT_DATA | CONFLICTING_EVIDENCE

NO_SIGNAL   = no valid detection occurred recently.
NEUTRAL     = strategy evaluated, no directional bias right now.
WAITING     = preliminary condition exists, confirmation incomplete.
INVALIDATED = a detection's invalidation level was broken against it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from strategies.registry import REGISTRY

# strategies whose detections describe the same price move — used by the
# confluence dedupe (§7), exposed here for the schema's related-strategy fields
CORRELATED_GROUPS: dict[str, list[str]] = {
    "structure": ["smc_mss", "ict_mss"],
    "sweep": ["smc_liquidity_sweep"],
    "zones": ["smc_fvg", "smc_order_block", "smc_breaker"],
    "levels": ["ict_pdh_pdl", "ict_asian_range"],
}

# verdict window per interval: how fresh a detection must be to count as the
# strategy's standing verdict (in bars)
FRESH_WINDOW_BARS = {"1min": 60, "5min": 48, "15min": 32, "30min": 24, "1h": 24, "4h": 16, "1day": 5}
BAR_MINUTES = {"1min": 1, "5min": 5, "15min": 15, "30min": 30, "1h": 60, "4h": 240, "1day": 1440}

MIN_CANDLES = 60


def _interval_delta(interval: str) -> timedelta:
    return timedelta(minutes=BAR_MINUTES.get(interval, 60))


def classify(
    strategy_id: str,
    strategy_name: str,
    detections: list[dict],
    last_close: float | None,
    interval: str,
    n_candles: int,
    now: datetime | None = None,
) -> dict:
    """Classify one strategy's standing verdict from its detections (newest first)."""
    now = now or datetime.now(UTC)
    base: dict[str, Any] = {
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "timeframe": interval,
        "evaluated_at": now.isoformat(),
        "verdict": "NO_SIGNAL",
        "signal_status": None,
        "direction": None,
        "reference_price": None,
        "entry_zone": None,
        "invalidation_level": None,
        "take_profit_levels": [],
        "evidence": [],
        "conditions_met": [],
        "conditions_missing": [],
        "last_detection": None,
        "algorithm_version": None,
        "data_quality": "FRESH" if n_candles >= MIN_CANDLES else "INSUFFICIENT",
    }

    if n_candles < MIN_CANDLES:
        base["verdict"] = "INSUFFICIENT_DATA"
        return base

    fresh_bars = FRESH_WINDOW_BARS.get(interval, 24)
    fresh_cutoff = now - _interval_delta(interval) * fresh_bars

    latest = detections[0] if detections else None

    if latest is None:
        return base  # NO_SIGNAL

    anchor = latest["anchor_time"]
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=UTC)
    base["last_detection"] = anchor.isoformat()
    base["algorithm_version"] = latest.get("algo_version")
    base["evidence"] = latest.get("evidence") or []
    levels = latest.get("levels") or {}
    direction = latest.get("direction")

    # find a plausible reference + invalidation from the level dict
    ref_keys = ("overlap_low", "entry_low", "sweep_low", "level", "low")
    ref_price = next((levels[k] for k in ref_keys if levels.get(k) is not None), None)
    invalidation = levels.get("stop")
    base["reference_price"] = ref_price
    base["invalidation_level"] = invalidation
    if "overlap_high" in levels or "entry_high" in levels:
        lo = levels.get("overlap_low", levels.get("entry_low"))
        hi = levels.get("overlap_high", levels.get("entry_high"))
        if lo is not None and hi is not None:
            base["entry_zone"] = {"low": lo, "high": hi}

    stale = anchor < fresh_cutoff

    # invalidation check: for bullish, price below invalidation kills it
    if (
        not stale
        and invalidation is not None
        and last_close is not None
        and (
            (direction == "bullish" and last_close < float(invalidation))
            or (direction == "bearish" and last_close > float(invalidation))
        )
    ):
        base["verdict"] = "INVALIDATED"
        base["signal_status"] = "INVALIDATED"
        base["conditions_met"] = ["detection formed", "invalidation level broken against the signal"]
        return base

    if stale:
        base["verdict"] = "NO_SIGNAL"
        base["signal_status"] = "EXPIRED"
        base["conditions_missing"] = ["a fresh detection within the verdict window"]
        return base

    if direction in ("bullish", "bearish"):
        base["verdict"] = "BULLISH" if direction == "bullish" else "BEARISH"
        base["signal_status"] = "CONFIRMED" if latest.get("status") == "active" else latest.get("status", "CONFIRMED").upper()
        base["direction"] = "LONG" if direction == "bullish" else "SHORT"
        base["conditions_met"] = ["detection confirmed on closed candles"]
        return base

    # neutral-direction detection (structure events etc.)
    base["verdict"] = "NEUTRAL"
    base["signal_status"] = "OBSERVED"
    return base


def related_strategies(strategy_id: str) -> list[str]:
    for members in CORRELATED_GROUPS.values():
        if strategy_id in members:
            return [m for m in members if m != strategy_id]
    return []
