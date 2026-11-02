"""Macro intelligence API: series summary, CFTC positioning, calendar, news."""

from __future__ import annotations

import os

from fastapi import APIRouter, Query

from app.macrodata import (
    cftc_positioning,
    latest_news,
    macro_series_summary,
    upcoming_events,
)
from app.marketdata.provider_factory import load_provider  # noqa: F401 ( TwelveData parity)
from providers.cftc import CftcProvider
from providers.fred import FredProvider

router = APIRouter(prefix="/v1/macro", tags=["macro"])


def _fred() -> FredProvider:
    return FredProvider(api_key=os.environ.get("FRED_API_KEY") or None)


@router.get("/summary")
def summary() -> dict:
    return {
        "series": macro_series_summary(),
        "cftc": [
            {
                "series_id": r["series_id"],
                "title": r["title"],
                "as_of_date": r["as_of_date"].isoformat() if r["as_of_date"] else None,
                "net_noncomm": str(r["value"]) if r["value"] is not None else None,
                "details": r["meta"],
            }
            for r in cftc_positioning()
        ],
        "provider_health": {"fred": _fred().health(), "cftc": CftcProvider().health()},
    }


@router.get("/events")
def events(days_ahead: int = Query(default=30, ge=1, le=180), past_days: int = Query(default=14, ge=1, le=90)) -> dict:
    rows = upcoming_events(days_ahead, past_days)
    return {
        "count": len(rows),
        "events": [
            {
                "release_name": r["release_name"],
                "series_id": r["series_id"],
                "event_date": r["event_date"].isoformat() if r["event_date"] else None,
                "actual_value": str(r["actual_value"]) if r["actual_value"] is not None else None,
                "units": r["units"],
            }
            for r in rows
        ],
    }


@router.get("/news")
def news(limit: int = Query(default=20, ge=1, le=100)) -> dict:
    rows = latest_news(limit)
    return {
        "count": len(rows),
        "articles": [
            {
                "source": r["source"],
                "url": r["url"],
                "title": r["title"],
                "summary": r["summary"],
                "published_at": r["published_at"].isoformat() if r["published_at"] else None,
                "classified": r["classified"],
                "sentiment": r["sentiment"],
            }
            for r in rows
        ],
    }
