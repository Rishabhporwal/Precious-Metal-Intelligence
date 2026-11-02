"""LLM output validation — schema + the number-containment guarantee.

Number-containment: every numeric literal in the LLM narrative must exist in
the evidence numbers (within 1% relative tolerance, or exact small-integer
allowlist for counts/horizons). Violations fail validation; the graph retries
once, then falls back to the deterministic builder.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pydantic

from ai.prompts import PROMPT_VERSION  # noqa: F401 — version coupled to validator

NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
SMALL_INT_ALLOWLIST = set(range(31))  # counts/horizons (3 scenarios, 5d, 20d, 48h...)


def evidence_numbers(evidence: dict, risk: dict) -> set[float]:
    """All numeric values in the evidence + risk structures (flattened)."""
    numbers: set[float] = set()

    def walk(v: Any) -> None:
        if isinstance(v, bool):
            return
        if isinstance(v, (int, float)):
            f = float(v)
            numbers.add(f)
            numbers.add(round(f, 1))
            numbers.add(round(f, 2))
            # rounded-to-int variants (e.g. evidence 3915.016 -> "3915" allowed)
            numbers.add(float(round(f)))
        elif isinstance(v, str):
            stripped = v.strip()
            try:
                numbers.add(float(stripped))
            except ValueError:
                for m in NUM_RE.finditer(stripped):
                    try:
                        numbers.add(float(m.group()))
                    except ValueError:
                        pass
        elif isinstance(v, dict):
            for vv in v.values():
                walk(vv)
        elif isinstance(v, list):
            for vv in v:
                walk(vv)

    walk(evidence)
    walk(risk)
    return numbers


def number_violations(text: str, allowed: set[float]) -> list[str]:
    violations = []
    # indicator names embed periods (EMA200, RSI14...) — strip before extraction
    text = re.sub(
        r"\b(?:EMA|SMA|RSI|ADX|ATR|ROC|STOCH|HV|RV|MACD|DGS|DFII|DCOIL|DTWEX)\s?-?\d+\b",
        "",
        text,
        flags=re.IGNORECASE,
    )
    for m in NUM_RE.finditer(text):
        raw = m.group()
        try:
            v = float(raw)
        except ValueError:
            continue
        if v in SMALL_INT_ALLOWLIST:
            continue
        # tight tolerance: LLM may round to 2dp at most (roundings pre-added to
        # the allowed set) — a 1% window would let invented levels slip through
        ok = any(abs(v - a) <= max(abs(a) * 0.0005, 0.02) for a in allowed)
        if not ok:
            violations.append(raw)
    return violations


class Scenario(pydantic.BaseModel):
    direction: str = pydantic.Field(pattern="^(bullish|neutral|bearish)$")
    narrative: str
    supporting: list[str] = []
    conflicting: list[str] = []
    confirmation: str = ""
    invalidation: str = ""


class AnalysisOut(pydantic.BaseModel):
    summary: str
    scenarios: list[Scenario]
    data_warnings: list[str] = []


def validate_llm_output(content: str, evidence: dict, risk: dict) -> tuple[AnalysisOut | None, list[str]]:
    """Returns (validated, errors). Errors empty => usable."""
    errors: list[str] = []
    # strip accidental markdown fences
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"```\s*$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, [f"invalid JSON: {exc}"]
    try:
        out = AnalysisOut.model_validate(data)
    except pydantic.ValidationError as exc:
        return None, [f"schema violation: {exc}"]

    directions = [s.direction for s in out.scenarios]
    if len(out.scenarios) != 3:
        errors.append(f"expected exactly 3 scenarios, got {len(out.scenarios)}")
    for needed in ("bullish", "neutral", "bearish"):
        if needed not in directions:
            errors.append(f"missing {needed} scenario")

    allowed = evidence_numbers(evidence, risk)
    blob = json.dumps([s.model_dump() for s in out.scenarios]) + out.summary
    bad = number_violations(blob, allowed)
    if bad:
        errors.append(f"numbers not present in evidence: {bad[:8]}")
    if errors:
        return None, errors
    return out, []
