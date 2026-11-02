"""Leakage verification — the anti-repaint gate.

For every detection used in a backtest, re-run the strategy on the candle
PREFIX up to (and including) the anchor bar. A genuine non-repainting detection
must appear in the prefix run; if it doesn't, the detection depended on future
data and is EXCLUDED from the backtest (counted in `leakage_excluded`).
"""

from __future__ import annotations

import logging
from datetime import datetime

from strategies.base import build_context
from strategies.registry import REGISTRY

logger = logging.getLogger("backtest")


def verify_detection_prefix(
    strategy_id: str,
    anchor_index: int,
    rows: list[dict],
    daily: list[dict],
    hourly: list[dict],
    params: dict | None = None,
) -> bool:
    """True if the detection at anchor_index exists when only data ≤ anchor is visible."""
    cls = REGISTRY.get(strategy_id)
    if cls is None:
        return False
    prefix = rows[: anchor_index + 1]
    if len(prefix) < 60:
        return False
    ctx = build_context(rows[0].get("symbol", "XAUUSD"), "1h", prefix, daily, hourly, params=params)
    merged = {**(cls.default_params or {}), **(params or {})}
    try:
        dets = cls().detect(ctx)
    except Exception as exc:  # noqa: BLE001
        logger.warning("prefix re-run failed for %s: %s", strategy_id, exc)
        return False
    anchor_time: datetime = rows[anchor_index]["market_ts"]
    target = anchor_time if isinstance(anchor_time, datetime) else datetime.fromisoformat(str(anchor_time))
    for d in dets:
        d_time = d.anchor_time if isinstance(d.anchor_time, datetime) else datetime.fromisoformat(str(d.anchor_time))
        if d_time == target:
            return True
    return False
