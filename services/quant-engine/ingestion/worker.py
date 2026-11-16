"""Market data ingestion worker.

Owns: historical backfill + incremental updates for enabled instruments.
Runs as a separate compose service (same quant image, different command):
    python -m ingestion

Honest behavior: instruments are ingested only when entitlement_verified AND
enabled (set by the /verify flow). Nothing is fabricated when the provider is
unconfigured — the worker logs and idles.
"""

from __future__ import annotations

import logging
import os
import signal
import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.db import get_pool
from app.marketdata import store
from app.marketdata.provider_factory import load_provider
from providers.base import CandleInterval

if TYPE_CHECKING:
    from providers.twelve_data import TwelveDataProvider

logging.basicConfig(
    level=logging.getLevelNamesMapping().get(
        os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO
    ),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("ingestion")
# Never log provider URLs — they carry the API key as a query parameter.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

BACKFILL_INTERVALS = [CandleInterval.DAY_1, CandleInterval.HOUR_1]
BACKFILL_OUTPUTSIZE = int(os.environ.get("BACKFILL_OUTPUTSIZE", "5000"))
# Free-plan credit economy (8/min, 800/day):
#   quotes:   N_instruments x 1 credit every QUOTE_POLL_SECONDS
#   candles:  N_instruments x 1 credit every MIN_CANDLE_POLL_SECONDS
#   2 instruments: 576/day (quotes) + 192/day (1min refresh) ≈ 768/day — inside budget.
QUOTE_POLL_SECONDS = int(os.environ.get("QUOTE_POLL_SECONDS", "300"))
MIN_CANDLE_POLL_SECONDS = int(os.environ.get("MIN_CANDLE_POLL_SECONDS", "900"))


def enabled_instruments() -> list[dict]:
    with get_pool().connection() as conn:
        cur = conn.execute(
            """
            SELECT i.id, i.symbol, i.provider_symbol
            FROM instruments i
            JOIN data_providers p ON p.id = i.provider_id
            WHERE i.enabled AND i.entitlement_verified AND p.name = 'twelvedata'
            """
        )
        return cur.fetchall()


def twelvedata_provider_id() -> int:
    with get_pool().connection() as conn:
        cur = conn.execute("SELECT id FROM data_providers WHERE name = 'twelvedata'")
        row = cur.fetchone()
    if row is None:
        raise RuntimeError("twelvedata provider missing from data_providers — run seed script")
    return int(row["id"])


def ingest_quote(provider: TwelveDataProvider, instrument: dict, provider_id: int) -> None:
    symbol, provider_symbol = instrument["symbol"], instrument["provider_symbol"]
    try:
        quote = provider.fetch_quote(provider_symbol)
    except Exception as exc:  # noqa: BLE001 — worker must survive provider failures
        logger.warning("quote %s failed: %s", symbol, exc)
        return
    raw = {"symbol": provider_symbol, "price": str(quote.price), "market_ts": quote.market_ts.isoformat()}
    with get_pool().connection() as conn:
        store.record_observation(conn, provider_id, provider_symbol, "quote", raw, ok=True)
        store.upsert_quote(conn, instrument["id"], provider_id, quote)
    logger.info("quote %s = %s @ %s", symbol, quote.price, quote.market_ts.isoformat())


def ingest_candles(
    provider: TwelveDataProvider,
    instrument: dict,
    provider_id: int,
    interval: CandleInterval,
    outputsize: int,
    start: datetime | None = None,
) -> int:
    symbol, provider_symbol = instrument["symbol"], instrument["provider_symbol"]
    try:
        candles = provider.fetch_candles(provider_symbol, interval, start=start, limit=outputsize)
    except Exception as exc:  # noqa: BLE001
        logger.warning("candles %s %s failed: %s", symbol, interval.value, exc)
        return 0
    raw = {
        "symbol": provider_symbol,
        "interval": interval.value,
        "count": len(candles),
        "first": candles[0].market_ts.isoformat() if candles else None,
        "last": candles[-1].market_ts.isoformat() if candles else None,
    }
    with get_pool().connection() as conn:
        store.record_observation(conn, provider_id, provider_symbol, "time_series", raw, ok=True)
        written = store.upsert_candles(conn, instrument["id"], provider_id, interval, candles)
    logger.info("candles %s %s: %d rows", symbol, interval.value, written)
    # Provider clock-skew guard: a newest candle far in the future means the
    # provider ignored the timezone contract — flag loudly, never store blindly.
    latest = max(c.market_ts for c in candles)
    if latest > datetime.now(UTC) + timedelta(minutes=5):
        logger.warning(
            "candles %s %s: newest candle %s is in the FUTURE — provider clock skew, check timezone handling",
            symbol, interval.value, latest.isoformat(),
        )

    # Strategy evaluation hook: run the engine on intervals we evaluate.
    from providers.base import CandleInterval as CI
    from strategies.engine import EVAL_INTERVALS, run_evaluation

    if interval in EVAL_INTERVALS:
        try:
            result = run_evaluation(symbol, CI(interval.value))
            logger.info("strategies %s %s: %d persisted", symbol, interval.value,
                        result.get("detections_persisted", 0))
        except Exception as exc:  # noqa: BLE001 — detection failures never block ingestion
            logger.warning("strategy evaluation failed for %s %s: %s", symbol, interval.value, exc)
    return written


def _log_staleness(instruments: list[dict]) -> None:
    """ERROR loudly if any series is beyond its staleness threshold — silent
    staleness is how week-old levels end up on the UI looking current."""
    from app.dataquality import _staleness_threshold, data_age_hours
    from providers.base import CandleInterval

    for instrument in instruments:
        for interval in (CandleInterval.MIN_1, CandleInterval.HOUR_1, CandleInterval.DAY_1):
            age = data_age_hours(instrument["symbol"], interval)
            if age is None:
                logger.error("STALE DATA: %s %s has no candles at all", instrument["symbol"], interval.value)
                continue
            threshold = _staleness_threshold(interval) * 3 if interval is CandleInterval.MIN_1 else _staleness_threshold(interval)
            if age > threshold:
                logger.error(
                    "STALE DATA: %s %s newest candle is %.1fh old (threshold %.0fh) — "
                    "verdict levels computed from this will be wrong",
                    instrument["symbol"], interval.value, age, threshold,
                )


def run() -> None:
    logger.info("ingestion worker starting")
    stop = False

    def handle_signal(signum, _frame):
        nonlocal stop
        logger.info("received signal %s — shutting down", signum)
        stop = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    provider = load_provider()
    health = provider.health()
    logger.info("twelvedata: %s", health)
    if not health["credentials_configured"]:
        logger.warning(
            "TWELVEDATA_API_KEY not set — worker idles. Set the key and restart; "
            "no market data is fabricated in the meantime."
        )

    # Startup backfill for enabled instruments.
    instruments = enabled_instruments()
    if instruments:
        provider_id = twelvedata_provider_id()
        for instrument in instruments:
            for interval in BACKFILL_INTERVALS:
                ingest_candles(provider, instrument, provider_id, interval, BACKFILL_OUTPUTSIZE)

    last_candle_poll = 0.0
    last_hourly_poll = 0.0
    last_daily_poll = 0.0  # refresh immediately on first loop pass
    # Credit budget (free plan 800/day, gold only): quotes 288 + 1min 96 +
    # hourly refresh 48 + daily refresh 4 ≈ 436/day — leaves ~45% headroom.
    HOURLY_POLL_SECONDS = int(os.environ.get("HOURLY_POLL_SECONDS", "1800"))
    # Daily candles MUST refresh on a schedule, not only at startup — the verdict
    # engine's prev-day levels go stale otherwise (found: dailies frozen 5 days).
    DAILY_POLL_SECONDS = int(os.environ.get("DAILY_POLL_SECONDS", str(6 * 3600)))
    while not stop:
        cycle_start = time.monotonic()
        instruments = enabled_instruments()  # re-read: verify flow may enable new ones
        if instruments:
            provider_id = twelvedata_provider_id()
            now_wall = time.monotonic()
            do_min = now_wall - last_candle_poll >= MIN_CANDLE_POLL_SECONDS
            do_hour = now_wall - last_hourly_poll >= HOURLY_POLL_SECONDS
            do_daily = now_wall - last_daily_poll >= DAILY_POLL_SECONDS
            for instrument in instruments:
                if stop:
                    break
                ingest_quote(provider, instrument, provider_id)
                if do_min:
                    # Refresh the most recent 1min candles (covers corrections too).
                    ingest_candles(
                        provider, instrument, provider_id, CandleInterval.MIN_1,
                        outputsize=10,
                        start=datetime.now(UTC) - timedelta(minutes=30),
                    )
                if do_hour:
                    # Keep the hourly series live — strategies and verdicts run on it.
                    ingest_candles(
                        provider, instrument, provider_id, CandleInterval.HOUR_1,
                        outputsize=30,
                        start=datetime.now(UTC) - timedelta(hours=36),
                    )
                if do_daily:
                    # Keep the daily series live — verdict prev-day/S/R levels are
                    # computed from it. Small window; 1 credit per 6h.
                    ingest_candles(
                        provider, instrument, provider_id, CandleInterval.DAY_1,
                        outputsize=30,
                        start=datetime.now(UTC) - timedelta(days=45),
                    )
            if do_min:
                last_candle_poll = time.monotonic()
            if do_hour:
                last_hourly_poll = time.monotonic()
            if do_daily:
                last_daily_poll = time.monotonic()
                _log_staleness(instruments)
        else:
            logger.info("no enabled instruments yet — idling")
        # sleep until next quote poll, remaining responsive to shutdown
        elapsed = time.monotonic() - cycle_start
        for _ in range(max(1, int((QUOTE_POLL_SECONDS - elapsed) // 2))):
            if stop:
                break
            time.sleep(2)
    logger.info("ingestion worker stopped")


if __name__ == "__main__":
    run()
