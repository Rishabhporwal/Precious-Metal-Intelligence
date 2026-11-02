"""Twelve Data adapter unit tests — offline, HTTP mocked. No real API calls."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from providers import twelve_data as td_module
from providers.base import (
    CandleInterval,
    NormalizedQuote,
    ProviderAuthError,
    ProviderError,
    ProviderUnconfigured,
    RateLimitError,
    SymbolUnavailable,
    VolumeType,
)
from providers.twelve_data import TwelveDataProvider


@pytest.fixture
def provider():
    return TwelveDataProvider(
        api_key="test-key",
        requests_per_minute=600,  # fast bucket for tests
        daily_budget=100000,
        max_retries=1,
    )


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


def test_fetch_candles_normalizes_ascending_and_labels_tick_volume(provider, monkeypatch):
    payload = {
        "values": [
            {"datetime": "2026-10-02", "open": "2650.1", "high": "2660.0", "low": "2640.5", "close": "2655.2", "volume": "12345"},
            {"datetime": "2026-10-01", "open": "2640.0", "high": "2655.9", "low": "2635.0", "close": "2650.1"},
        ]
    }
    monkeypatch.setattr(td_module.httpx, "get", lambda *a, **k: FakeResponse(payload))
    candles = provider.fetch_candles("XAU/USD", CandleInterval.DAY_1)

    assert len(candles) == 2
    # ascending by time despite provider returning newest-first
    assert candles[0].market_ts < candles[1].market_ts
    assert candles[0].market_ts == datetime(2026, 10, 1, tzinfo=UTC)
    assert candles[0].close == Decimal("2650.1")
    # no volume key -> VolumeType.NONE, never fabricated exchange volume
    assert candles[0].volume is None
    assert candles[0].volume_type is VolumeType.NONE
    # volume key present -> honestly labeled tick volume
    assert candles[1].volume_type is VolumeType.TICK
    # newest candle is provisional (possibly still forming)
    assert candles[1].status == "provisional"
    assert candles[0].status == "final"


def test_unconfigured_provider_raises_and_never_fakes():
    p = TwelveDataProvider(api_key=None)
    with pytest.raises(ProviderUnconfigured):
        p.fetch_quote("XAU/USD")
    with pytest.raises(ProviderUnconfigured):
        p.verify_instrument("XAU/USD")


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"code": 401, "message": "Invalid API key"}, ProviderAuthError),
        ({"code": 429, "message": "rate limit"}, RateLimitError),
        ({"code": 404, "message": "symbol XAU/USD not available for free plan"}, SymbolUnavailable),
        ({"code": 400, "message": "bad request"}, ProviderError),
    ],
)
def test_provider_error_mapping(provider, monkeypatch, payload, expected):
    monkeypatch.setattr(td_module.httpx, "get", lambda *a, **k: FakeResponse(payload))
    with pytest.raises(expected):
        provider.fetch_quote("XAU/USD")


def test_quote_normalization(provider, monkeypatch):
    payload = {
        "symbol": "XAU/USD", "timestamp": 1799000000, "close": "4005.25",
        "open": "3998.10", "high": "4010.00", "low": "3995.50",
    }
    monkeypatch.setattr(td_module.httpx, "get", lambda *a, **k: FakeResponse(payload))
    quote = provider.fetch_quote("XAU/USD")
    assert isinstance(quote, NormalizedQuote)
    assert quote.price == Decimal("4005.25")
    assert quote.market_ts.tzinfo is not None
    # bid/ask absent -> None, not fabricated
    assert quote.bid is None and quote.ask is None


def test_retry_on_5xx_then_success(provider, monkeypatch):
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResponse({}, status=503)
        return FakeResponse({"values": [{"datetime": "2026-10-01", "open": "1", "high": "1", "low": "1", "close": "1"}]})

    monkeypatch.setattr(td_module.httpx, "get", flaky)
    monkeypatch.setattr(td_module.time, "sleep", lambda s: None)
    candles = provider.fetch_candles("XAU/USD", CandleInterval.DAY_1)
    assert calls["n"] == 2
    assert len(candles) == 1


def test_verify_instrument_success_flow(provider, monkeypatch):
    quote_payload = {"symbol": "XAU/USD", "timestamp": 1799000000, "close": "4005.25"}
    ts_payload = {
        "values": [
            {"datetime": "2026-10-02", "open": "1", "high": "1", "low": "1", "close": "1"},
            {"datetime": "2026-10-01", "open": "1", "high": "1", "low": "1", "close": "1"},
        ]
    }

    def route(url, **kwargs):  # endpoint-aware mock: /quote vs /time_series
        return FakeResponse(quote_payload if url.endswith("/quote") else ts_payload)

    monkeypatch.setattr(td_module.httpx, "get", route)
    result = provider.verify_instrument("XAU/USD")
    assert result.available is True
    assert result.history_ok is True
    assert result.history_from == datetime(2026, 10, 1, tzinfo=UTC)
    assert "verified against live API" in result.note
