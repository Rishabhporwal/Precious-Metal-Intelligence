"""CFTC Commitments of Traders adapter (public Socrata API — no key needed).

Dataset: CFTC "Futures Only Reports" (legacy) on publicreporting.cftc.gov.
We track gold and silver futures positioning (non-commercial long/short/spread =
"managed/leveraged money" proxy in the legacy report, honestly labeled).

Docs: https://dev.socrata.com/foundry/publicreporting.cftc.gov/6dca-aqww
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger("cftc")

BASE_URL = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"

MARKETS = {
    "GOLD": "GOLD - COMMODITY EXCHANGE INC.",
    "SILVER": "SILVER - COMMODITY EXCHANGE INC.",
}


class CftcProvider:
    name = "cftc"

    def __init__(self, timeout_s: float = 20.0):
        self.timeout_s = timeout_s

    def health(self) -> dict:
        return {"provider": self.name, "credentials_configured": True}  # public API

    def latest_positioning(self, market_code: str, limit: int = 8) -> list[dict]:
        """Latest COT rows for a market, newest first, parsed to a compact dict."""
        name = MARKETS.get(market_code.upper())
        if not name:
            raise ValueError(f"unknown CFTC market {market_code}")
        params = {
            "$where": f"market_and_exchange_names = '{name}'",
            "$order": "report_date_as_yyyy_mm_dd DESC",
            "$limit": limit,
        }
        resp = httpx.get(BASE_URL, params=params, timeout=self.timeout_s)
        resp.raise_for_status()
        rows = resp.json()
        out = []
        for r in rows:
            out.append({
                "report_date": (r.get("report_date_as_yyyy_mm_dd") or "")[:10],
                "open_interest": _num(r.get("open_interest_all")),
                "noncomm_long": _num(r.get("noncomm_positions_long_all")),
                "noncomm_short": _num(r.get("noncomm_positions_short_all")),
                "noncomm_spreading": _num(r.get("noncomm_positions_spreading_all")),
                "comm_long": _num(r.get("comm_positions_long_all")),
                "comm_short": _num(r.get("comm_positions_short_all")),
                "change_in_noncomm_long": _num(r.get("change_in_noncomm_long_all")),
                "change_in_noncomm_short": _num(r.get("change_in_noncomm_short_all")),
                "pct_of_oi_noncomm_long": _num(r.get("pct_of_oi_noncomm_long_all")),
                "pct_of_oi_noncomm_short": _num(r.get("pct_of_oi_noncomm_short_all")),
            })
        return out

    def fetch_all_positioning(self) -> list[dict]:
        rows = []
        for code in MARKETS:
            try:
                for r in self.latest_positioning(code):
                    net = (
                        (r["noncomm_long"] or 0) - (r["noncomm_short"] or 0)
                        if r["noncomm_long"] is not None and r["noncomm_short"] is not None
                        else None
                    )
                    rows.append({
                        "provider": "cftc",
                        "series_id": f"COT_{code}",
                        "title": f"CFTC Futures-Only COT — {code.title()}",
                        "units": "contracts",
                        "as_of_date": r["report_date"],
                        "value": net,  # net non-commercial position
                        "meta": r,
                    })
            except Exception as exc:  # noqa: BLE001
                logger.warning("CFTC market %s failed: %s", code, exc)
        return rows


def _num(v) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None
