"""FRED macro adapter.

Docs: https://fred.stlouisfed.org/docs/api/fred/

Series watchlist (gold-relevant macro):
- DGS2 / DGS10: nominal Treasury yields
- DFII10: 10y real yield (TIPS)
- DTWEXBGS: broad trade-weighted US dollar index (DXY is proprietary ICE data —
  FRED carries the Fed's trade-weighted index instead; labeled honestly)
- CPIAUCSL (CPI), PCEPI (PCE), PAYEMS (nonfarm payrolls), UNRATE (unemployment)
- DCOILWTICO (WTI spot, daily)

All observations are stored append-only with fetch vintage (spec: preserve
publication vintages). Values come only from the live API — never fabricated.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

logger = logging.getLogger("fred")

BASE_URL = "https://api.stlouisfed.org"

SERIES_WATCHLIST = {
    "DGS2": "Market Yield on U.S. Treasury Securities at 2-Year Constant Maturity",
    "DGS10": "Market Yield on U.S. Treasury Securities at 10-Year Constant Maturity",
    "DFII10": "10-Year Treasury Inflation-Indexed Security Constant Maturity",
    "DTWEXBGS": "Nominal Broad U.S. Dollar Index (trade-weighted; DXY proxy)",
    "CPIAUCSL": "Consumer Price Index for All Urban Consumers",
    "PCEPI": "Personal Consumption Expenditures Price Index",
    "PAYEMS": "All Employees, Total Nonfarm (nonfarm payrolls)",
    "UNRATE": "Unemployment Rate",
    "DCOILWTICO": "Crude Oil Prices: WTI — Cushing, Oklahoma (daily spot)",
}

# Releases we track for the economic calendar (FRED release IDs)
RELEASE_WATCHLIST = {
    "10": "Consumer Price Index (CPI)",
    "50": "Employment Situation (NFP / Unemployment)",
    "53": "Personal Income and Outlays (PCE)",
}


class FredProvider:
    name = "fred"

    def __init__(self, api_key: str | None, timeout_s: float = 15.0):
        self.api_key = api_key
        self.timeout_s = timeout_s

    def health(self) -> dict:
        return {"provider": self.name, "credentials_configured": bool(self.api_key)}

    def _get(self, path: str, params: dict) -> dict:
        if not self.api_key:
            raise RuntimeError("FRED_API_KEY is not set — macro data cannot be fetched.")
        resp = httpx.get(
            f"{BASE_URL}{path}",
            params={**params, "api_key": self.api_key, "file_type": "json"},
            timeout=self.timeout_s,
        )
        if resp.status_code == 400:
            body = resp.json()
            msg = body.get("error_message", "bad request")
            if "api_key" in msg.lower():
                raise RuntimeError(f"FRED rejected the API key: {msg}")
            raise RuntimeError(f"FRED error: {msg}")
        resp.raise_for_status()
        return resp.json()

    def latest_observations(self, series_id: str, limit: int = 26) -> list[dict]:
        """Latest observations, ascending, as {date, value(float|None), as_of}."""
        body = self._get(
            "/fred/series/observations",
            {"series_id": series_id, "sort_order": "desc", "limit": limit},
        )
        out = []
        for obs in body.get("observations", []):
            raw = obs.get("value")
            out.append({
                "date": obs.get("date"),
                "value": float(raw) if raw not in (None, ".") else None,
            })
        out.reverse()
        return out

    def series_meta(self, series_id: str) -> dict:
        body = self._get("/fred/series", {"series_id": series_id})
        s = body.get("seriess", [{}])[0]
        return {"title": s.get("title"), "units": s.get("units"), "frequency": s.get("frequency")}

    def release_dates(self, release_id: str, limit: int = 6) -> list[dict]:
        """Release dates (includes scheduled future dates)."""
        body = self._get(
            "/fred/release/dates",
            {"release_id": release_id, "sort_order": "desc", "limit": limit, "include_release_dates_with_no_data": "true"},
        )
        return [{"date": r["date"]} for r in body.get("release_dates", [])]

    def fetch_all_observations(self) -> list[dict]:
        """Fetch latest observations for the whole watchlist. Returns rows ready to store."""
        rows = []
        for series_id in SERIES_WATCHLIST:
            try:
                meta = self.series_meta(series_id)
                obs = self.latest_observations(series_id, limit=14)
            except Exception as exc:  # noqa: BLE001 — per-series isolation
                logger.warning("FRED series %s failed: %s", series_id, exc)
                continue
            for o in obs:
                rows.append({
                    "provider": "fred",
                    "series_id": series_id,
                    "title": meta.get("title"),
                    "units": meta.get("units"),
                    "as_of_date": o["date"],
                    "value": o["value"],
                    "meta": {"frequency": meta.get("frequency"), "fetched": datetime.now(UTC).isoformat()},
                })
        return rows
