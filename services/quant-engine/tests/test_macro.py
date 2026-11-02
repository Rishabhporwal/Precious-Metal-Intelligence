"""Macro/news adapter tests — offline, HTTP mocked. No real API calls."""

import pytest

from providers import cftc as cftc_mod
from providers import fred as fred_mod
from providers import news_rss as news_mod
from providers.cftc import CftcProvider
from providers.fred import FredProvider
from providers.news_rss import fetch_feed


class FakeResponse:
    def __init__(self, payload, status=200, content: bytes = b""):
        self._payload = payload
        self.status_code = status
        self.content = content

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_unconfigured_fred_raises(monkeypatch):
    f = FredProvider(api_key=None)
    with pytest.raises(RuntimeError):
        f.latest_observations("DGS10")


def test_fred_observations_normalization(monkeypatch):
    f = FredProvider(api_key="k")
    payload = {
        "observations": [  # FRED returns newest-first
            {"date": "2026-10-31", "value": "."},  # missing marker
            {"date": "2026-10-30", "value": "4.12"},
        ]
    }
    monkeypatch.setattr(fred_mod.httpx, "get", lambda *a, **k: FakeResponse(payload))
    obs = f.latest_observations("DGS10")
    # ascending order; missing value -> None, never fabricated
    assert obs[0]["date"] == "2026-10-30" and obs[0]["value"] == 4.12
    assert obs[1]["value"] is None


def test_fred_auth_error_surfaced(monkeypatch):
    f = FredProvider(api_key="bad")
    payload = {"error_message": "The api_key provided is not valid."}
    monkeypatch.setattr(fred_mod.httpx, "get", lambda *a, **k: FakeResponse(payload, status=400))
    with pytest.raises(RuntimeError, match="rejected the API key"):
        f.latest_observations("DGS10")


def test_cftc_parse(monkeypatch):
    c = CftcProvider()
    rows = [{
        "report_date_as_yyyy_mm_dd": "2026-10-27T00:00:00.000",
        "open_interest_all": "456789",
        "noncomm_positions_long_all": "250000",
        "noncomm_positions_short_all": "80000",
        "noncomm_positions_spreading_all": "1234",
        "comm_positions_long_all": "200000",
        "comm_positions_short_all": "370000",
        "change_in_noncomm_long_all": "-5000",
        "change_in_noncomm_short_all": "1000",
        "pct_of_oi_noncomm_long_all": "54.7",
        "pct_of_oi_noncomm_short_all": "17.5",
    }]
    monkeypatch.setattr(cftc_mod.httpx, "get", lambda *a, **k: FakeResponse(rows))
    parsed = c.latest_positioning("GOLD")
    assert parsed[0]["report_date"] == "2026-10-27"
    assert parsed[0]["noncomm_long"] == 250000.0
    # net long computed downstream = 250000 - 80000 = 170000
    all_rows = c.fetch_all_positioning()
    gold = next(r for r in all_rows if r["series_id"] == "COT_GOLD")
    assert gold["value"] == 170000.0


RSS_SAMPLE = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
<item>
  <title>Gold holds near record</title>
  <link>https://example.com/gold-1</link>
  <description>&lt;b&gt;Bullion&lt;/b&gt; steadied.</description>
  <pubDate>Mon, 02 Nov 2026 10:00:00 +0000</pubDate>
</item>
<item>
  <title>No link item</title>
  <description>x</description>
</item>
</channel></rss>"""


def test_news_rss_parse(monkeypatch):
    monkeypatch.setattr(
        news_mod.httpx, "get",
        lambda *a, **k: FakeResponse({}, content=RSS_SAMPLE),
    )
    articles = fetch_feed("yahoo_gold", "http://fake")
    assert len(articles) == 1  # linkless item skipped
    a = articles[0]
    assert a["title"] == "Gold holds near record"
    assert a["url"] == "https://example.com/gold-1"
    assert "<b>" not in a["summary"]  # HTML stripped — untrusted content sanitized
    assert a["published_at"] is not None and a["published_at"].year == 2026
