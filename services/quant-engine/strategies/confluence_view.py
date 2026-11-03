"""Multi-strategy confluence (new spec §7): compare independent verdicts,
dedupe correlated signals, produce a transparent interpretation."""

from __future__ import annotations

from strategies.verdicts import CORRELATED_GROUPS


def build_confluence(verdicts: list[dict]) -> dict:
    """verdicts: output of the strategy-verdict engine (list of schema dicts).

    Rules:
    - correlated strategies (same underlying move) count ONCE — the strongest
      directional verdict in the group carries the group's weight.
    - weights by evidence family: structure 1.5, sweep 1.2, zones 1.0,
      levels 0.6, patterns 0.8, wyckoff 1.0, other 0.5.
    - the score is transparent arithmetic, NOT a probability of success.
    """
    group_of: dict[str, str] = {}
    for gname, members in CORRELATED_GROUPS.items():
        for m in members:
            group_of[m] = gname

    WEIGHTS = {
        "structure": 1.5,
        "sweep": 1.2,
        "zones": 1.0,
        "levels": 0.6,
        "patterns": 0.8,
        "wyckoff": 1.0,
    }

    def weight_for(v: dict) -> float:
        return WEIGHTS.get(group_of.get(v["strategy_id"], "other"), 0.5)

    directional = [v for v in verdicts if v["verdict"] in ("BULLISH", "BEARISH")]
    supporting: list[dict] = []
    conflicting: list[dict] = []

    # group dedupe: pick the verdict with the largest |vote basis| per group
    seen_groups: dict[str, dict] = {}
    ungrouped_used: set[str] = set()
    for v in sorted(directional, key=lambda x: x["strategy_id"]):
        g = group_of.get(v["strategy_id"])
        if g is None:
            ungrouped_used.add(v["strategy_id"])
            (supporting if v["verdict"] == "BULLISH" else conflicting).append(v)
        elif g not in seen_groups or abs(seen_groups[g].get("_w", 0)) < abs(weight_for(v)):
            seen_groups[g] = {**v, "_w": weight_for(v)}
    for g, v in seen_groups.items():
        (supporting if v["verdict"] == "BULLISH" else conflicting).append(v)

    def net(items: list[dict]) -> float:
        return sum(weight_for(v) * (1 if v["verdict"] == "BULLISH" else -1) for v in items)

    bull_net = net([v for v in supporting])
    bear_net = net([v for v in conflicting])
    score = round(bull_net + bear_net, 2)

    n_bull = sum(1 for v in verdicts if v["verdict"] == "BULLISH")
    n_bear = sum(1 for v in verdicts if v["verdict"] == "BEARISH")
    n_neutral = sum(1 for v in verdicts if v["verdict"] == "NEUTRAL")
    n_none = sum(1 for v in verdicts if v["verdict"] == "NO_SIGNAL")
    n_insuff = sum(1 for v in verdicts if v["verdict"] == "INSUFFICIENT_DATA")
    n_invalid = sum(1 for v in verdicts if v["verdict"] == "INVALIDATED")
    n_wait = sum(1 for v in verdicts if v["verdict"] == "WAITING_FOR_CONFIRMATION")

    if abs(score) >= 2.5 and n_bull * n_bear == 0:
        interpretation = "BULLISH CONFLUENCE" if score > 0 else "BEARISH CONFLUENCE"
        tone = "strong"
    elif abs(score) >= 1.0:
        interpretation = "LEAN BULLISH" if score > 0 else "LEAN BEARISH"
        tone = "moderate"
    else:
        interpretation = "MIXED / NO CONFLUENCE"
        tone = "mixed"

    def evidence_lines(items: list[dict]) -> list[str]:
        seen_groups_local: set[str] = set()
        lines: list[str] = []
        for v in items:
            g = group_of.get(v["strategy_id"])
            if g and g in seen_groups_local:
                continue
            if g:
                seen_groups_local.add(g)
            if v["evidence"]:
                lines.append(f"{v['strategy_name']}: {v['evidence'][0]}")
            else:
                lines.append(f"{v['strategy_name']}: {v['verdict'].lower()} verdict")
        return lines

    return {
        "counts": {
            "bullish": n_bull,
            "bearish": n_bear,
            "neutral": n_neutral,
            "no_signal": n_none,
            "insufficient_data": n_insuff,
            "invalidated": n_invalid,
            "waiting": n_wait,
        },
        "score": score,
        "interpretation": interpretation,
        "tone": tone,
        "supporting": evidence_lines(supporting),
        "conflicting": evidence_lines(conflicting),
        "dedupe_note": (
            "Related strategies describing the same price move are counted once "
            "(strongest verdict carries the group weight) — no double-counting."
        ),
        "method": "transparent weighted arithmetic; NOT a calibrated probability of success",
    }
