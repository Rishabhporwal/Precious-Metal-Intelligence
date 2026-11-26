"""Crypto order-flow ingestion (BTC/ETH/SOL) on the OpenMarket free tier.

Budget math (1,000 weight/day, every query 1x weight):
  per-side candles every 15 min : 3 x 96 = 288
  OI + funding every 30 min     : 6 x 48 = 288
  liquidations hourly           : 3 x 24 = 72
  total ≈ 648/day — ~35% headroom for retries.
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.db import get_pool
from providers import openmarket as om

logger = logging.getLogger("ingestion.crypto")

SYMBOLS = om.SYMBOLS
CANDLE_LOOKBACK = 48 * 3600  # 48h of hourly candles per poll
DERIV_LOOKBACK = 26 * 3600
LIQ_LOOKBACK = 26 * 3600


def _upsert_candles(symbol: str, bars: list[dict]) -> int:
    if not bars:
        return 0
    with get_pool().connection() as conn:
        for b in bars:
            conn.execute(
                """
                INSERT INTO crypto_candles
                    (symbol, market_ts, open, high, low, close, buy_volume, sell_volume, exchanges)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1)
                ON CONFLICT (symbol, market_ts) DO UPDATE SET
                    open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                    close = EXCLUDED.close, buy_volume = EXCLUDED.buy_volume,
                    sell_volume = EXCLUDED.sell_volume
                """,
                (symbol, b["market_ts"], b["open"], b["high"], b["low"], b["close"],
                 b["buy_volume"], b["sell_volume"]),
            )
    return len(bars)


def _upsert_deriv(symbol: str, oi: list[dict], funding: list[dict], liq: dict[str, list[dict]]) -> int:
    series: dict[datetime, dict] = {}
    for row in oi:
        series.setdefault(row["market_ts"], {})["open_interest"] = row["value"]
    for row in funding:
        series.setdefault(row["market_ts"], {})["funding_rate"] = row["value"]
    for side, rows in liq.items():
        for row in rows:
            series.setdefault(row["market_ts"], {})[f"liq_{side}"] = row["value"]
    n = 0
    with get_pool().connection() as conn:
        for ts, vals in sorted(series.items()):
            conn.execute(
                """
                INSERT INTO crypto_deriv
                    (symbol, market_ts, open_interest, funding_rate, liq_buy, liq_sell)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, market_ts) DO UPDATE SET
                    open_interest = COALESCE(EXCLUDED.open_interest, crypto_deriv.open_interest),
                    funding_rate = COALESCE(EXCLUDED.funding_rate, crypto_deriv.funding_rate),
                    liq_buy = COALESCE(EXCLUDED.liq_buy, crypto_deriv.liq_buy),
                    liq_sell = COALESCE(EXCLUDED.liq_sell, crypto_deriv.liq_sell)
                """,
                (symbol, ts, vals.get("open_interest"), vals.get("funding_rate"),
                 vals.get("liq_buy"), vals.get("liq_sell")),
            )
            n += 1
    return n


def sync_candles() -> int:
    if not _configured():
        return 0
    n = 0
    for coin in SYMBOLS:
        try:
            bars = om.parse_candles(om.get_points(om.CANDLES, coin, "HOUR", CANDLE_LOOKBACK))
            n += _upsert_candles(coin, bars)
        except Exception as exc:  # noqa: BLE001 — one coin failing must not stop the rest
            logger.warning("crypto candles %s failed: %s", coin, exc)
    logger.info("crypto candles: %s bars stored", n)
    return n


def sync_deriv() -> int:
    if not _configured():
        return 0
    n = 0
    for coin in SYMBOLS:
        try:
            oi = om.parse_scalar(om.get_points(om.OPEN_INTEREST, coin, "HOUR", DERIV_LOOKBACK), ("openInterest", "oi", "value", "v"))
            funding = om.parse_scalar(om.get_points(om.FUNDING, coin, "HOUR", DERIV_LOOKBACK), ("fundingRate", "funding_rate", "value", "v"))
            liq = {}
            for side, key in (("buy", ("buyNotional", "buy_notional", "buy")), ("sell", ("sellNotional", "sell_notional", "sell"))):
                liq[side] = om.parse_scalar(om.get_points(om.LIQUIDATIONS, coin, "HOUR", LIQ_LOOKBACK), (key,))
            n += _upsert_deriv(coin, oi, funding, liq)
        except Exception as exc:  # noqa: BLE001
            logger.warning("crypto deriv %s failed: %s", coin, exc)
    logger.info("crypto deriv: %s rows stored", n)
    return n


_warned = False


def _configured() -> bool:
    global _warned
    try:
        om.api_key()
        return True
    except om.OpenMarketNotConfigured:
        if not _warned:
            _warned = True
            logger.warning(
                "crypto order-flow disabled: OPENMARKET_API_KEY not set — "
                "add the free key from openmarket.xyz account settings to enable BTC/ETH/SOL"
            )
        return False
