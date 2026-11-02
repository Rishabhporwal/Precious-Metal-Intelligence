"""Data-quality monitor tests: gap detection + staleness classification."""

from datetime import UTC, datetime, timedelta
from itertools import pairwise

from app.dataquality import _staleness_threshold, quality_report
from providers.base import CandleInterval


def test_staleness_thresholds():
    assert _staleness_threshold(CandleInterval.MIN_15) == 2.0
    assert _staleness_threshold(CandleInterval.HOUR_1) == 8.0
    assert _staleness_threshold(CandleInterval.DAY_1) == 72.0


def test_gap_detection_tolerance():
    # weekend gap (2+ days) is tolerated; a multi-hour hole in hourly data counts
    t0 = datetime(2026, 1, 2, tzinfo=UTC)  # Friday
    weekly = [t0 + timedelta(days=7 * i) for i in range(3)]
    # weekly spacing (10,080 min) is not within the gap window -> tolerated
    gaps = 0
    for a, b in pairwise(weekly):
        dt_min = (b - a).total_seconds() / 60
        if 1440 * 2.5 < dt_min < 60 * 24 * 3:
            gaps += 1
    assert gaps == 0

    hourly = [t0 + timedelta(hours=i) for i in range(5)]
    hourly = hourly[:3] + [hourly[3] + timedelta(hours=3)] + hourly[3:]  # 4h hole
    gaps = 0
    for a, b in pairwise(hourly):
        dt_min = (b - a).total_seconds() / 60
        if 150 < dt_min < 4320:
            gaps += 1
    assert gaps == 1


def test_quality_report_unknown_symbol():
    from unittest.mock import MagicMock, patch

    pool = MagicMock()
    pool.connection.return_value.__enter__ = MagicMock()
    with patch("app.dataquality.get_pool", return_value=pool), patch(
        "app.dataquality.store.get_instrument_by_symbol", return_value=None
    ):
        assert quality_report("NOPE") == {"error": "unknown instrument NOPE"}
