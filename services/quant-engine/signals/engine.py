"""Signal Engine (enhancement spec §2.2, §9): the 9-state decision layer.

Separates SIGNAL GENERATION from evidence SOURCES: it consumes the strategy
verdict snapshot + regime + event risk, reconciles them with dedupe weights,
and emits exactly one standing signal per symbol/interval:

  BUY | STRONG_BUY | SELL | STRONG_SELL | EARLY_BUY | EARLY_SELL
  WAIT | NO_TRADE | INVALIDATED

Rules:
- Early signals (EARLY_*) fire on |score| >= 1.0 with momentum-family
  leadership but incomplete cross-group confirmation — explicitly labeled
  lower confidence, smaller risk allowed.
- Confirmed signals (BUY/SELL) require |score| >= 2.2 with >= 2 independent
  evidence groups agreeing AND no high-impact event veto.
- STRONG_* requires |score| >= 3.2 AND the regime confirming direction.
- WAIT: meaningful lean but confirmation missing. NO_TRADE: nothing useful.
- Every signal gets an expiry (default 24 bars) and an invalidation level.
- Outcome grading is deterministic: after expiry/invalidation the price path
  from signal time is scored into signal_outcomes (R-multiple, MFE/MAE).
- The score is transparent arithmetic — NOT a calibrated probability.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from strategies.verdicts import CORRELATED_GROUPS

WEIGHTS = {
    "structure": 1.5,
    "sweep": 1.2,
    "zones": 1.0,
    "levels": 0.6,
    "patterns": 0.8,
    "wyckoff": 1.0,
    "sessions": 0.9,
    "trend": 1.2,
    "breakout": 1.1,
    "other": 0.5,
}

GROUP_OF = {m: g for g, members in CORRELATED_GROUPS.items() for m in members}

# momentum strategies count as "momentum leadership" for EARLY classification
MOMENTUM_IDS = {"mom_trend_cont", "mom_breakout_retest", "mom_range_breakout",
                "mom_expansion", "mom_ema_align", "mom_hh_hl", "mom_pullback",
                "mom_mtf_align"}

# coarse EVIDENCE FAMILIES for the early/confirmed distinction (§2.2): several
# strategies inside one family are related evidence, not independent confirmations
FAMILY_OF: dict[str, str] = {}


def _family(sid: str) -> str:
    if sid.startswith("mom_"):
        return "momentum"
    if sid.startswith(("smc_", "ict_")) or sid.startswith("price_action_"):
        return "smc"
    if sid.startswith("wyckoff_"):
        return "wyckoff"
    if sid.startswith("quant_"):
        return "quant"
    return "other"


for _sid in MOMENTUM_IDS:
    FAMILY_OF[_sid] = "momentum"


def _freshness(v: dict) -> str:
    return v.get("last_detection") or ""


def _regime_classify(regime: dict, score: float) -> str:
    """Named regime per enhancement spec §8, from quant regime states + score."""
    trend = (regime.get("trend") or {}).get("trend", "sideways")
    strength = (regime.get("strength") or {}).get("strength", "weak")
    vol = (regime.get("vol") or {}).get("vol_regime", "normal")
    if vol == "high" and abs(score) >= 2:
        return "high-volatility breakout"
    if trend == "up":
        return "strong bullish trend" if strength == "strong" else "weak bullish trend"
    if trend == "down":
        return "strong bearish trend" if strength == "strong" else "weak bearish trend"
    if vol == "low":
        return "low-volatility consolidation"
    return "sideways / range-bound"


def _strategy_relevance(regime_name: str) -> list[str]:
    """Which strategy families matter most under this regime (§8: explain, don't hide)."""
    if "trend" in regime_name and "weak" not in regime_name:
        return ["Momentum & trend-following (trend continuation, pullbacks, breakouts)",
                "Multi-timeframe alignment", "Volatility expansion for adds"]
    if "consolidation" in regime_name or "range" in regime_name:
        return ["Liquidity sweeps and range boundaries", "Failed breakouts", "Mean-reversion caution"]
    if "high-volatility" in regime_name:
        return ["Event-driven momentum", "Cross-market confirmation", "Reduced position risk"]
    return ["All families equally weighted — no dominant regime"]


def decide(
    verdicts: list[dict],
    regime: dict,
    event_veto: bool,
    veto_events: list[dict],
    price: float,
    prev_open_signal: dict | None,
    plan_levels: dict | None,
    interval: str,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(UTC)
    group_of = GROUP_OF

    def weight_for(v: dict) -> float:
        return WEIGHTS.get(group_of.get(v["strategy_id"], "other"), 0.5)

    # dedupe correlated verdicts: strongest directional verdict per group carries the weight
    seen: dict[str, dict] = {}
    singles: list[dict] = []
    for v in verdicts:
        if v["verdict"] not in ("BULLISH", "BEARISH"):
            continue
        g = group_of.get(v["strategy_id"])
        if g is None:
            singles.append(v)
            continue
        # freshest evidence carries the group weight (§7: no double-counting)
        prev = seen.get(g)
        if prev is None or _freshness(v) > _freshness(prev):
            seen[g] = v
    deduped = list(seen.values()) + singles

    bull = [v for v in deduped if v["verdict"] == "BULLISH"]
    bear = [v for v in deduped if v["verdict"] == "BEARISH"]
    bull_score = sum(weight_for(v) for v in bull)
    bear_score = sum(weight_for(v) for v in bear)
    score = round(bull_score - bear_score, 2)

    # independence count: distinct COARSE evidence families on the dominant side
    # (two momentum strategies = one momentum family, not two confirmations — §2.2)
    dominant = bull if score > 0 else bear
    families_agreeing = len({_family(v["strategy_id"]) for v in dominant})
    groups_agreeing = len({group_of.get(v["strategy_id"], "other:" + v["strategy_id"]) for v in dominant})
    momentum_leading = any(v["strategy_id"] in MOMENTUM_IDS for v in dominant)

    # regime confirmation
    regime_name = _regime_classify(regime, score)
    regime_confirms = (score > 0 and "bullish" in regime_name and "weak" not in regime_name) or (
        score < 0 and "bearish" in regime_name and "weak" not in regime_name
    )

    # INVALIDATED: previous open signal's invalidation broken against it
    if (
        prev_open_signal
        and prev_open_signal.get("invalidation_level") is not None
        and prev_open_signal.get("signal_type") in ("BUY", "STRONG_BUY", "EARLY_BUY")
        and price < float(prev_open_signal["invalidation_level"])
    ):
        return _signal("INVALIDATED", score, regime_name, verdicts, price, now, interval,
                       note="prior long invalidation level broken — signal void", event_veto=event_veto)
    if (
        prev_open_signal
        and prev_open_signal.get("invalidation_level") is not None
        and prev_open_signal.get("signal_type") in ("SELL", "STRONG_SELL", "EARLY_SELL")
        and price > float(prev_open_signal["invalidation_level"])
    ):
        return _signal("INVALIDATED", score, regime_name, verdicts, price, now, interval,
                       note="prior short invalidation level broken — signal void", event_veto=event_veto)

    if event_veto:
        st = _signal("WAIT", score, regime_name, verdicts, price, now, interval,
                     note="high-impact event within 48h — signals suppressed, watch reaction",
                     event_veto=True)
        st["veto_events"] = veto_events
        return st

    abs_score = abs(score)
    direction = "bull" if score > 0 else "bear"

    if abs_score >= 3.2 and families_agreeing >= 2 and regime_confirms:
        st = _signal("STRONG_BUY" if score > 0 else "STRONG_SELL", score, regime_name, verdicts,
                     price, now, interval, plan=plan_levels, event_veto=False)
    elif abs_score >= 2.2 and families_agreeing >= 2:
        st = _signal("BUY" if score > 0 else "SELL", score, regime_name, verdicts,
                     price, now, interval, plan=plan_levels, event_veto=False)
    elif abs_score >= 1.0 and momentum_leading:
        st = _signal("EARLY_BUY" if score > 0 else "EARLY_SELL", score, regime_name, verdicts,
                     price, now, interval, event_veto=False)
        st["early_rationale"] = (
            "Momentum leadership present but cross-family confirmation incomplete — smaller size, tighter invalidation."
        )
    elif abs_score >= 0.6:
        st = _signal("WAIT", score, regime_name, verdicts, price, now, interval,
                     note="a lean exists but evidence is not sufficient to act", event_veto=False)
    else:
        st = _signal("NO_TRADE", score, regime_name, verdicts, price, now, interval, event_veto=False)

    st["score"] = score
    st["groups_agreeing"] = families_agreeing
    st["regime_confirms"] = regime_confirms
    st["momentum_leading"] = momentum_leading
    st["strategy_relevance"] = _strategy_relevance(regime_name)
    return st


def _signal(
    signal_type: str,
    score: float,
    regime_name: str,
    verdicts: list[dict],
    price: float,
    now: datetime,
    interval: str,
    plan: dict | None = None,
    event_veto: bool = False,
    note: str | None = None,
) -> dict:
    bars = {"15min": 32, "1h": 24, "4h": 16, "1day": 5}.get(interval, 24)
    invalidation = None
    if plan and plan.get("stop") is not None:
        invalidation = plan["stop"]
    drivers = [
        {"strategy": v["strategy_name"], "verdict": v["verdict"], "plain": (v["evidence"] or [""])[0]}
        for v in verdicts if v["verdict"] in ("BULLISH", "BEARISH")
    ]
    return {
        "signal_type": signal_type,
        "score": score,
        "price": price,
        "regime": regime_name,
        "drivers": drivers,
        "plan": plan,
        "invalidation_level": invalidation,
        "expires_at": (now + timedelta(minutes={"15min": 15, "1h": 60, "4h": 240, "1day": 1440}.get(interval, 60) * bars)).isoformat(),
        "confidence": "high" if signal_type.startswith("STRONG") else "medium" if signal_type in ("BUY", "SELL") else "low",
        "note": note,
        "event_veto": event_veto,
    }


def grade(
    signal: dict,
    highs_after: list[float],
    lows_after: list[float],
    closes_after: list[float],
) -> dict:
    """Deterministic outcome grading (enhancement spec §10): what actually happened.

    Walks the price path after the signal in bar order: stop hit, target hit, or
    expiry close. Returns R-multiple, MFE/MAE, and exit reason. No hindsight
    reinterpretation — the path is evaluated in order.
    """
    plan = signal.get("plan") or {}
    direction = 1 if signal["signal_type"] in ("BUY", "STRONG_BUY", "EARLY_BUY") else -1
    entry = float(signal["price"])
    stop = plan.get("stop")
    t1 = plan.get("t1")
    if stop is None or t1 is None:
        # no plan (WAIT/early) — grade direction only against expiry close
        if not closes_after:
            return {"graded": False, "reason": "no forward data"}
        move = (closes_after[-1] - entry) * direction
        return {
            "graded": True, "exit_reason": "expiry", "r_multiple": None,
            "direction_move_pct": round(move / entry * 100, 3),
            "mfe": round(max((h - entry) * direction for h in highs_after) / entry * 100, 3),
            "mae": round(max((entry - l) * direction for l in lows_after) / entry * 100, 3),
        }
    risk = abs(entry - stop)
    if risk <= 0:
        return {"graded": False, "reason": "degenerate risk"}
    mfe, mae = 0.0, 0.0
    for h, l in zip(highs_after, lows_after, strict=False):
        fav = (h - entry) * direction
        adv = (entry - l) * direction
        mfe = max(mfe, fav)
        mae = max(mae, adv)
        stop_hit = l <= stop if direction == 1 else h >= stop
        t1_hit = h >= t1 if direction == 1 else l <= t1
        if stop_hit and t1_hit:
            return {"graded": True, "exit_reason": "stop+target same bar (pessimistic: stop)", "r_multiple": -1.0,
                    "mfe": round(mfe / risk, 2), "mae": round(mae / risk, 2)}
        if stop_hit:
            return {"graded": True, "exit_reason": "stop", "r_multiple": -1.0,
                    "mfe": round(mfe / risk, 2), "mae": round(mae / risk, 2)}
        if t1_hit:
            return {"graded": True, "exit_reason": "target", "r_multiple": 1.0,
                    "mfe": round(mfe / risk, 2), "mae": round(mae / risk, 2)}
    if closes_after:
        move = (closes_after[-1] - entry) * direction
        return {"graded": True, "exit_reason": "expiry", "r_multiple": round(move / risk, 2),
                "mfe": round(mfe / risk, 2), "mae": round(mae / risk, 2)}
    return {"graded": False, "reason": "no forward data"}
