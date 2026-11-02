"""Risk engine: setup construction from composite detections, validation gates,
position sizing. Deterministic; instrument-specific contract specs."""

from __future__ import annotations

from dataclasses import dataclass

RISK_ENGINE_VERSION = "risk-1.0.0"

# Instrument contract specs (unit of size = oz for metals, lot conventions later).
# value_per_unit_per_price = P&L in quote currency per 1.0 price move per 1 size unit.
CONTRACT_SPECS = {
    "XAUUSD": {"unit": "oz", "value_per_unit_per_price": 1.0},
    "XAGUSD": {"unit": "oz", "value_per_unit_per_price": 1.0},
}

DEFAULTS = {
    "min_rr": 1.5,
    "risk_pct_per_trade": 1.0,      # % of equity risked per trade
    "account_equity": 1000.0,       # user capital context
    "max_quote_age_min": 15,
    "event_risk_block_hours": 48,
    "min_stop_atr_frac": 0.3,       # stop must be >= 0.3 ATR away from entry
}


@dataclass(frozen=True)
class SetupCandidate:
    direction: str  # long | short
    entry_low: float
    entry_high: float
    stop: float
    target1: float
    target2: float | None
    target3: float | None
    anchor_time: str
    detection_id: int
    evidence: list[str]


def _atr(symbol: str) -> float | None:
    from app.db import get_pool
    from app.marketdata import store
    from indicators import atr as atr_fn
    from providers.base import CandleInterval

    with get_pool().connection() as conn:
        inst = store.get_instrument_by_symbol(conn, symbol)
        if inst is None:
            return None
        daily = store.get_candles(conn, inst["id"], CandleInterval.DAY_1, limit=30)
    if len(daily) < 15:
        return None
    highs = [float(r["high"]) for r in daily]
    lows = [float(r["low"]) for r in daily]
    closes = [float(r["close"]) for r in daily]
    s = atr_fn(highs, lows, closes, 14)
    return next((v for v in reversed(s) if v is not None), None)


def candidate_from_detection(detection: dict, atr: float | None) -> SetupCandidate | None:
    """Build a SetupCandidate from a composite strategy detection (1h)."""
    if detection["strategy_id"] != "composite_sweep_mss_fvg_ob":
        return None
    levels = detection.get("levels") or {}
    direction = "long" if detection["direction"] == "bullish" else "short"
    # entry zone: FVG∩OB overlap if present, else FVG zone
    if "overlap_low" in levels:
        entry_low, entry_high = float(levels["overlap_low"]), float(levels["overlap_high"])
    elif "entry_low" in levels:
        entry_low, entry_high = float(levels["entry_low"]), float(levels["entry_high"])
    else:
        return None
    stop = levels.get("stop")
    if stop is None:
        return None
    stop = float(stop)
    entry_ref = entry_low if direction == "long" else entry_high
    risk = abs(entry_ref - stop)
    if risk <= 0 or atr is None:
        return None
    sign = 1 if direction == "long" else -1
    t1 = entry_ref + sign * 1.0 * risk
    t2 = entry_ref + sign * 2.0 * risk
    t3 = entry_ref + sign * 3.0 * risk
    return SetupCandidate(
        direction=direction,
        entry_low=entry_low,
        entry_high=entry_high,
        stop=stop,
        target1=t1,
        target2=t2,
        target3=t3,
        anchor_time=str(detection.get("anchor_time")),
        detection_id=int(detection["id"]),
        evidence=[f"R/R(1) = {risk and abs(t1 - entry_ref) / risk:.2f}"],
    )


def validate(candidate: SetupCandidate, symbol: str, params: dict | None = None) -> tuple[bool, list[str], float | None]:
    """Validation gate. Returns (valid, reasons, position_size)."""
    p = {**DEFAULTS, **(params or {})}
    reasons: list[str] = []

    from datetime import UTC, datetime

    from app.db import get_pool
    from app.marketdata import store

    entry_ref = candidate.entry_low if candidate.direction == "long" else candidate.entry_high

    # 1. data freshness
    with get_pool().connection() as conn:
        inst = store.get_instrument_by_symbol(conn, symbol)
        if inst is None:
            return False, [f"unknown instrument {symbol}"], None
        q = store.get_latest_quote(conn, inst["id"])
        events = conn.execute(
            """
            SELECT release_name, event_date FROM economic_events
            WHERE event_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 2
            """
        ).fetchall()
    if q is None or q["received_at"] is None:
        reasons.append("no fresh quote available")
    else:
        age_min = (datetime.now(UTC) - q["received_at"]).total_seconds() / 60
        if age_min > p["max_quote_age_min"]:
            reasons.append(f"quote stale ({age_min:.0f} min > {p['max_quote_age_min']})")
    price = float(q["price"]) if q and q["price"] is not None else None

    # 2. entry still valid — price must not have run far beyond the zone
    if price is not None:
        if candidate.direction == "long" and price < entry_ref:
            reasons.append(f"price {price:.4f} already below entry zone ({entry_ref:.4f}) — missed")
        if candidate.direction == "short" and price > entry_ref:
            reasons.append(f"price {price:.4f} already above entry zone ({entry_ref:.4f}) — missed")

    # 3. stop sanity: minimum distance from entry
    atr = _atr(symbol)
    if atr is None:
        reasons.append("ATR unavailable — cannot sanity-check stop")
    else:
        stop_distance = abs(entry_ref - candidate.stop)
        if stop_distance < p["min_stop_atr_frac"] * atr:
            reasons.append(
                f"stop too tight ({stop_distance:.4f} < {p['min_stop_atr_frac']} ATR = {p['min_stop_atr_frac'] * atr:.4f})"
            )
        # stop must be on the correct side
        if candidate.direction == "long" and candidate.stop >= entry_ref:
            reasons.append("stop not below entry for long")
        if candidate.direction == "short" and candidate.stop <= entry_ref:
            reasons.append("stop not above entry for short")

    # 4. minimum R/R
    risk = abs(entry_ref - candidate.stop)
    rr = abs(candidate.target1 - entry_ref) / risk if risk > 0 else 0
    if rr < p["min_rr"]:
        reasons.append(f"R/R {rr:.2f} below minimum {p['min_rr']}")

    # 5. event risk policy
    if events:
        names = ", ".join(e["release_name"] for e in events)
        reasons.append(f"high-impact event within {p['event_risk_block_hours']}h: {names}")

    # 6. position sizing (deterministic)
    size = None
    spec = CONTRACT_SPECS.get(symbol)
    if spec and risk > 0:
        risk_amount = p["account_equity"] * p["risk_pct_per_trade"] / 100.0
        size = risk_amount / (risk * spec["value_per_unit_per_price"])
        if size <= 0:
            reasons.append("position size rounds to zero")

    valid = len(reasons) == 0
    return valid, reasons, size


def position_preview(symbol: str, entry: float, stop: float, params: dict | None = None) -> dict:
    """Sizing preview used by the UI (no persistence)."""
    p = {**DEFAULTS, **(params or {})}
    spec = CONTRACT_SPECS.get(symbol, {"unit": "units", "value_per_unit_per_price": 1.0})
    risk_amount = p["account_equity"] * p["risk_pct_per_trade"] / 100.0
    distance = abs(entry - stop)
    size = risk_amount / distance if distance > 0 else 0.0
    return {
        "unit": spec["unit"],
        "risk_amount": round(risk_amount, 2),
        "stop_distance": round(distance, 4),
        "position_size": round(size, 4),
        "notional": round(size * entry, 2),
        "note": "sizing preview only — paper trading, never live execution",
    }
