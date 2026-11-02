"""LLM output validation tests — the number-containment guarantee."""

import json

from ai.validate import number_violations, validate_llm_output

EVIDENCE = {
    "technical": {
        "daily_indicators": {"rsi14": 32.7, "ema200": 4255.95},
        "structure_1h": {
            "supports": [{"price": 3890.1, "touches": 2}],
            "resistances": [{"price": 3915.0, "touches": 3}],
            "prev_day": {"high": 3915.0, "low": 3866.0},
        },
    },
    "quant": {"correlations": [{"series_id": "DTWEXBGS", "rolling_30d": -0.206}]},
}
RISK = {"atr14_daily": 58.266, "platform_reference_stop_distance": 87.399}


def _allowed():
    from ai.validate import evidence_numbers

    return evidence_numbers(EVIDENCE, RISK)


def test_numbers_from_evidence_pass():
    text = "RSI 32.7 with EMA200 at 4255.95; correlation -0.206; ATR 58.27 suggests stop distance 87.4."
    assert number_violations(text, _allowed()) == []


def test_invented_levels_flagged():
    text = "Target 4310.50 and stop 3899.99."
    violations = number_violations(text, _allowed())
    assert "4310.50" in violations
    assert "3899.99" in violations


def test_small_int_allowlist():
    text = "Over 3 scenarios and 20-day horizon, expect a move."
    assert number_violations(text, _allowed()) == []


def test_valid_llm_output_passes_full_validation():
    content = json.dumps({
        "summary": "Down trend per quant.regime with RSI 32.7.",
        "scenarios": [
            {"direction": "bullish", "narrative": "Hold above support 3890.1.",
             "supporting": ["technical.structure_1h.supports"], "conflicting": [],
             "confirmation": "hold above supports", "invalidation": "close below 3890.1"},
            {"direction": "neutral", "narrative": "Range between 3890.1 and 3915.0.",
             "supporting": [], "conflicting": [], "confirmation": "oscillation",
             "invalidation": "decisive close"},
            {"direction": "bearish", "narrative": "Rejection at resistance 3915.0 favors retest.",
             "supporting": ["quant.regime"], "conflicting": [],
             "confirmation": "rejection", "invalidation": "close above 3915.0"},
        ],
        "data_warnings": [],
    })
    out, errors = validate_llm_output(content, EVIDENCE, RISK)
    assert out is not None, errors
    assert len(out.scenarios) == 3


def test_llm_output_with_invented_number_fails():
    content = json.dumps({
        "summary": "Read.",
        "scenarios": [
            {"direction": "bullish", "narrative": "Target 4310.50 — invented.",
             "supporting": [], "conflicting": [], "confirmation": "x", "invalidation": "x"},
            {"direction": "neutral", "narrative": "ok", "supporting": [], "conflicting": [],
             "confirmation": "x", "invalidation": "x"},
            {"direction": "bearish", "narrative": "ok", "supporting": [], "conflicting": [],
             "confirmation": "x", "invalidation": "x"},
        ],
        "data_warnings": [],
    })
    out, errors = validate_llm_output(content, EVIDENCE, RISK)
    assert out is None
    assert any("not present in evidence" in e for e in errors)


def test_missing_scenario_direction_fails_schema():
    content = json.dumps({"summary": "x", "scenarios": [{"direction": "sideways", "narrative": "x"}]})
    out, errors = validate_llm_output(content, EVIDENCE, RISK)
    assert out is None
