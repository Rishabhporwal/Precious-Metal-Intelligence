"""Scheduler service: macro/calendar/CFTC/news polling on fixed intervals.

Runs as its own compose service (same quant image):
    python -m scheduler

Intervals (seconds, env-overridable):
- FRED macro observations: every 6h
- FRED release calendar:   every 12h
- CFTC positioning:        every 12h (reports are weekly, Fri data)
- News RSS:                every 30 min
Failures log and never crash the loop; nothing is fabricated.
"""

from __future__ import annotations

import logging
import os
import time

from app.db import get_pool
from app.macrodata import (
    insert_economic_events,
    insert_macro_observations,
    insert_news,
)
from providers.cftc import CftcProvider
from providers.fred import RELEASE_WATCHLIST, FredProvider
from providers.news_rss import fetch_all_news

logging.basicConfig(
    level=logging.getLevelNamesMapping().get(os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("scheduler")
logging.getLogger("httpx").setLevel(logging.WARNING)

MACRO_INTERVAL = int(os.environ.get("MACRO_INTERVAL_SECONDS", str(6 * 3600)))
CALENDAR_INTERVAL = int(os.environ.get("CALENDAR_INTERVAL_SECONDS", str(12 * 3600)))
CFTC_INTERVAL = int(os.environ.get("CFTC_INTERVAL_SECONDS", str(12 * 3600)))
NEWS_INTERVAL = int(os.environ.get("NEWS_INTERVAL_SECONDS", "1800"))
ANALYSIS_INTERVAL = int(os.environ.get("ANALYSIS_INTERVAL_SECONDS", str(12 * 3600)))
TRADING_INTERVAL = int(os.environ.get("TRADING_INTERVAL_SECONDS", "120"))


def sync_macro(fred: FredProvider) -> None:
    if not fred.api_key:
        logger.warning("FRED_API_KEY not set — macro sync skipped (no data is fabricated)")
        return
    rows = fred.fetch_all_observations()
    written = insert_macro_observations(rows)
    logger.info("FRED sync: %d observations fetched, %d new rows", len(rows), written)


def sync_calendar(fred: FredProvider) -> None:
    if not fred.api_key:
        return
    events = []
    for release_id, name in RELEASE_WATCHLIST.items():
        try:
            for d in fred.release_dates(release_id, limit=6):
                events.append({
                    "source": "fred_release",
                    "release_name": name,
                    "series_id": None,
                    "event_date": d["date"],
                    "actual_value": None,
                    "units": None,
                })
        except Exception as exc:  # noqa: BLE001
            logger.warning("release %s failed: %s", release_id, exc)
    written = insert_economic_events(events)
    logger.info("calendar sync: %d release dates, %d new rows", len(events), written)


def sync_cftc(cftc: CftcProvider) -> None:
    rows = cftc.fetch_all_positioning()
    written = insert_macro_observations(rows)
    logger.info("CFTC sync: %d rows fetched, %d new rows", len(rows), written)


def sync_news() -> None:
    articles = fetch_all_news()
    written = insert_news(articles)
    logger.info("news sync: %d articles fetched, %d new rows", len(articles), written)


def sync_analysis() -> None:
    """Daily AI analyst run + news classification (LLM, cached)."""
    import asyncio

    from ai import graph as analyst_graph

    async def _run():
        result = await analyst_graph.run_analysis("XAUUSD", "1day")
        logger.info("analysis: status=%s cache=%s", result.get("status"),
                    (result.get("llm_meta") or {}).get("cache_hit"))
        try:
            from app.api.analyst import classify_news

            cls = await classify_news(limit=30)
            logger.info("news classification: %s", cls)
        except Exception as exc:  # noqa: BLE001
            logger.warning("news classification skipped: %s", exc)

    asyncio.run(_run())


def sync_trading() -> None:
    """Paper-trade SL/TP monitoring, alert evaluation, setup evaluation (cheap, local)."""
    from app import alerts, paper

    closed = paper.monitor_open_trades()
    alert_counts = alerts.evaluate_all()
    setups = 0
    try:
        import httpx

        r = httpx.post(
            "http://localhost:8001/v1/strategies/evaluate_setups?symbol=XAUUSD&interval=1h",
            timeout=60,
        )
        if r.status_code == 200:
            setups = r.json().get("valid_created", 0)
    except Exception as exc:  # noqa: BLE001
        logger.debug("setup evaluation skipped: %s", exc)
    logger.info("trading sync: closed=%s alerts=%s new_valid_setups=%s", closed, alert_counts, setups)


def run() -> None:
    logger.info("scheduler starting (macro %ss / calendar %ss / cftc %ss / news %ss)",
                MACRO_INTERVAL, CALENDAR_INTERVAL, CFTC_INTERVAL, NEWS_INTERVAL)
    fred = FredProvider(api_key=os.environ.get("FRED_API_KEY") or None)
    cftc = CftcProvider()
    get_pool()  # open pool eagerly

    last = {"macro": 0.0, "calendar": 0.0, "cftc": 0.0, "news": 0.0}

    # initial syncs
    sync_macro(fred)
    last["macro"] = time.monotonic()
    sync_calendar(fred)
    last["calendar"] = time.monotonic()
    sync_cftc(cftc)
    last["cftc"] = time.monotonic()
    sync_news()
    last["news"] = time.monotonic()
    sync_analysis()
    paper.ensure_default_account()
    last["trading"] = time.monotonic()

    while True:
        time.sleep(30)
        now = time.monotonic()
        try:
            if now - last["macro"] >= MACRO_INTERVAL:
                sync_macro(fred)
                last["macro"] = now
            if now - last["calendar"] >= CALENDAR_INTERVAL:
                sync_calendar(fred)
                last["calendar"] = now
            if now - last["cftc"] >= CFTC_INTERVAL:
                sync_cftc(cftc)
                last["cftc"] = now
            if now - last["news"] >= NEWS_INTERVAL:
                sync_news()
                last["news"] = now
            if now - last.get("analysis", 0) >= ANALYSIS_INTERVAL:
                sync_analysis()
                last["analysis"] = now
            if now - last.get("trading", 0) >= TRADING_INTERVAL:
                sync_trading()
                last["trading"] = now
        except Exception:
            logger.exception("scheduler cycle failed")


if __name__ == "__main__":
    run()
