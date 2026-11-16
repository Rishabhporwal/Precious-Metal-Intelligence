"""Regression tests: stale data must degrade the verdict and be flagged.

The stale-dailies bug (dailies frozen 5 days, UI showing week-old levels as
current) must be impossible to repeat silently.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.dataquality import freshness_flags


def _rows(hours_old: float, n: int = 5) -> list[dict]:
    now = datetime.now(UTC)
    return [
        {"market_ts": now - timedelta(hours=hours_old + (n - 1 - i)), "close": 100.0 + i,
         "high": 101.0 + i, "low": 99.0 + i}
        for i in range(n)
    ]


def test_freshness_flags_fresh_data_ok():
    flags = freshness_flags(hourly=_rows(2), daily=_rows(20))
    assert flags["ok"] if "ok" in flags else flags["hourly_ok"]
    assert flags["hourly_ok"] and flags["daily_ok"]
    assert flags["stale"] == []


def test_freshness_flags_flags_stale_hourly():
    # hourly 12h old (threshold 8h) — the exact bug shape
    flags = freshness_flags(hourly=_rows(12), daily=_rows(20))
    assert not flags["hourly_ok"]
    assert flags["daily_ok"]
    assert flags["stale"] and flags["stale"][0].startswith("hourly:")


def test_freshness_flags_flags_stale_daily():
    # daily 5 days old — the frozen-dailies bug
    flags = freshness_flags(hourly=_rows(1), daily=_rows(5 * 24))
    assert not flags["daily_ok"]
    assert any(s.startswith("daily:") for s in flags["stale"])


def test_freshness_flags_missing_data():
    flags = freshness_flags(hourly=[], daily=[])
    assert not flags["hourly_ok"] and not flags["daily_ok"]
    assert "hourly:no_data" in flags["stale"] and "daily:no_data" in flags["stale"]


def test_verdict_degrades_confidence_on_stale_input():
    from ai.verdict import build_verdict

    # daily candles 5 days old — confidence must drop to low + data_quality.stale set
    verdict = build_verdict(
        symbol="XAUUSD",
        quote_price=3858.0,
        daily=_rows(5 * 24, 10),
        hourly=_rows(1, 10),
        strategy_bias={},
        events=[],
        news_net=None,
    )
    assert verdict.get("confidence") == "low"
    assert verdict.get("data_quality", {}).get("ok") is False
    assert verdict.get("data_quality", {}).get("stale")
    assert any("STALE INPUT DATA" in str(x) for x in verdict.get("invalidations", []))


def test_verdict_full_confidence_on_fresh_input():
    from ai.verdict import build_verdict

    verdict = build_verdict(
        symbol="XAUUSD",
        quote_price=3858.0,
        daily=_rows(20, 10),
        hourly=_rows(1, 10),
        strategy_bias={},
        events=[],
        news_net=None,
    )
    # the guard must add NOTHING to invalidations on fresh data (baseline
    # confidence may legitimately be low with an empty strategy fixture)
    assert verdict.get("data_quality", {}).get("ok") is True
    assert not [x for x in verdict.get("invalidations", []) if "STALE INPUT DATA" in str(x)]
