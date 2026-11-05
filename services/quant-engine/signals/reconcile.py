"""Evidence reconciliation (enhancement spec §9): four explicit verdicts before
the final call — Technical, Fundamental, Market Reaction, Quantitative — each
computed from its own evidence group, then reconciled into the final signal.

No group's verdict is hidden inside another's reasoning. Conflicts are
preserved, never resolved silently.
"""

from __future__ import annotations


def _net_verdict(bull: int, bear: int, neutral: int = 0) -> tuple[str, str]:
    total = bull + bear
    if total == 0:
        return "NEUTRAL", "no directional evidence in this group"
    margin = (bull - bear) / max(total, 1)
    if margin >= 0.6 and total >= 3:
        return "BULLISH", f"{bull} bullish vs {bear} bearish"
    if margin <= -0.6 and total >= 3:
        return "BEARISH", f"{bear} bearish vs {bull} bullish"
    if margin > 0.15:
        return "LEAN BULLISH", f"{bull} bullish vs {bear} bearish"
    if margin < -0.15:
        return "LEAN BEARISH", f"{bear} bearish vs {bull} bullish"
    return "MIXED", f"{bull} bullish vs {bear} bearish — no dominance"


def build_reconciliation(
    verdicts: list[dict],
    news_net: int | None,
    news_classified: int,
    high_impact_events: list[dict],
    reaction_counts: dict,
    regime: dict,
    cross_market: dict,
) -> dict:
    fam_counts: dict[str, dict[str, int]] = {}
    for v in verdicts:
        fam = _family(v["strategy_id"])
        c = fam_counts.setdefault(fam, {"bullish": 0, "bearish": 0, "neutral": 0, "no_signal": 0})
        key = v["verdict"].lower()
        c[key if key in c else "no_signal"] += 1

    tech_bull = sum(fam_counts.get(f, {}).get("bullish", 0) for f in ("momentum", "smc", "wyckoff"))
    tech_bear = sum(fam_counts.get(f, {}).get("bearish", 0) for f in ("momentum", "smc", "wyckoff"))
    tech_neutral = sum(fam_counts.get(f, {}).get("neutral", 0) + fam_counts.get(f, {}).get("no_signal", 0) for f in ("momentum", "smc", "wyckoff"))
    tech_v, tech_detail = _net_verdict(tech_bull, tech_bear, tech_neutral)
    smc_only = fam_counts.get("smc", {})
    quant_v, quant_detail = _net_verdict(
        fam_counts.get("quant", {}).get("bullish", 0), fam_counts.get("quant", {}).get("bearish", 0),
        fam_counts.get("quant", {}).get("no_signal", 0) + fam_counts.get("quant", {}).get("neutral", 0),
    )

    trend = (regime.get("trend") or {}).get("trend", "sideways")
    strength = (regime.get("strength") or {}).get("strength", "weak")
    vol = (regime.get("vol") or {}).get("vol_regime", "normal")
    quant_detail = f"regime: {trend} trend ({strength}), volatility {vol}; {quant_detail}"

    # fundamental: news sentiment + scheduled events + verification honesty
    if news_net is None or news_classified < 5:
        fund_v, fund_detail = "INSUFFICIENT DATA", (
            f"only {news_classified} classified articles — sentiment not established"
        )
    else:
        if news_net >= 2:
            fund_v = "BULLISH BIAS"
        elif news_net <= -2:
            fund_v = "BEARISH BIAS"
        elif news_net >= 1:
            fund_v = "LEAN BULLISH"
        elif news_net <= -1:
            fund_v = "LEAN BEARISH"
        else:
            fund_v = "NEUTRAL"
        fund_detail = f"news sentiment net {news_net:+d} over {news_classified} classified articles"
    if high_impact_events:
        fund_v = f"{fund_v} — EVENT RISK" if fund_v not in ("INSUFFICIENT DATA",) else fund_v
        fund_detail += f"; high-impact within 48h: {', '.join(e['release'] for e in high_impact_events[:2])}"

    # market reaction: what actually happened after recent events
    confirms = reaction_counts.get("confirms", 0)
    contradicts = reaction_counts.get("contradicts", 0)
    pending = reaction_counts.get("pending", 0)
    if confirms + contradicts == 0:
        reaction_v, reaction_detail = "INSUFFICIENT DATA", (
            f"{pending} events pending their post-window; none fully measured yet"
        )
    else:
        if confirms > contradicts * 2:
            reaction_v = "CONFIRMS BULLISH BIAS" if any(
                v["verdict"] == "BULLISH" for v in verdicts) else "CONFIRMS RECENT MOVES"
        elif contradicts > confirms * 2:
            reaction_v = "CONTRADICTS NEWS HYPOTHESES"
        else:
            reaction_v = "MIXED"
        reaction_detail = f"{confirms} event hypotheses confirmed, {contradicts} contradicted, {pending} pending, 0.15% noise floor"

    return {
        "technical": {"verdict": tech_v, "detail": tech_detail,
                      "smc_only": smc_only,
                      "by_family": {k: v for k, v in fam_counts.items()}},
        "fundamental": {"verdict": fund_v, "detail": fund_detail},
        "market_reaction": {"verdict": reaction_v, "detail": reaction_detail,
                            "counts": reaction_counts},
        "quantitative": {"verdict": quant_v, "detail": quant_detail},
        "cross_market": {
            "nudge": cross_market.get("nudge", 0.0),
            "detail": cross_market.get("note", ""),
            "supporting": cross_market.get("supporting", 0),
            "contradicting": cross_market.get("contradicting", 0),
        },
        "note": "each verdict is computed from its own evidence group; conflicts are shown, never silently resolved",
    }


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
