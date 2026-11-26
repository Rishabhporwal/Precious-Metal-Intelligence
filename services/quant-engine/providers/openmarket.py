"""OpenMarket Data API client (https://openmarket.xyz — public, documented
API, free tier: 10 weight/min / 1000 weight/day / 7-day history).

Crypto-only: BTC/ETH/SOL per-side trade candles (aggressive buys vs sells),
open interest, funding rates and liquidations. The key lives in
OPENMARKET_API_KEY; without it everything degrades honestly (no data, no
fabrication).

Response envelope (verified against the live API):
  {"series": [{"id": {..., "side": "BUY"|"SELL"|absent},
               "points": [{"Point": {...}, ...}, ...]}, ...]}
All timestamps are {"s": epoch_seconds} objects.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import httpx

BASE_URL = "https://api.openmarket.xyz/v1/points"
EXCHANGE = "BINANCE_FUTURES"  # single venue keeps every query at 1x weight
SYMBOLS = ("BTC", "ETH", "SOL")

CANDLES = "TRADE_AGG"  # per-side: one query returns BUY and SELL series
OPEN_INTEREST = "OPEN_INTEREST_AGG"
FUNDING = "FUNDING_RATE_AGG"
LIQUIDATIONS = "LIQUIDATION_AGG"


class OpenMarketNotConfigured(RuntimeError):
    pass


def api_key() -> str:
    key = os.environ.get("OPENMARKET_API_KEY", "").strip()
    if not key:
        raise OpenMarketNotConfigured("OPENMARKET_API_KEY not set")
    return key


def get_points(
    data_type: str,
    coin: str,
    interval: str,
    lookback_seconds: int,
    timeout: float = 30.0,
) -> dict:
    """One API call; returns the raw response body (1x weight for all v1 types)."""
    now = int(datetime.now(UTC).timestamp())
    params = {
        "type": data_type,
        "exchange": EXCHANGE,
        "rawSymbol": f"{coin}USDT",
        "interval": interval,
        "from": now - lookback_seconds,
        "period": lookback_seconds,  # period = the window length, not bar spacing
    }
    r = httpx.get(BASE_URL, params=params, headers={"X-OpenMarket-Key": api_key()}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def series_points(body: dict, side: str | None = None) -> list[tuple[datetime, dict]]:
    """Flatten the envelope to (timestamp, fields) for one side (or the sideless series)."""
    out: list[tuple[datetime, dict]] = []
    for series in body.get("series", []):
        sid = series.get("id") or {}
        if side is not None and sid.get("side") != side:
            continue
        if side is None and sid.get("side"):
            continue
        for p in series.get("points", []):
            point = p.get("Point") or {}
            ts = (point.get("timestamp") or {}).get("s")
            if ts is None:
                continue
            out.append((datetime.fromtimestamp(int(ts), tz=UTC), point))
    out.sort(key=lambda x: x[0])
    return out


def parse_candles(body: dict) -> list[dict]:
    """Merge the BUY and SELL series into one candle list with side volumes."""
    bars: dict[datetime, dict] = {}
    for ts, point in series_points(body, "BUY"):
        bars[ts] = {
            "market_ts": ts,
            "open": point.get("open"), "high": point.get("high"),
            "low": point.get("low"), "close": point.get("close"),
            "buy_volume": point.get("volume"), "sell_volume": None,
        }
    for ts, point in series_points(body, "SELL"):
        bar = bars.setdefault(ts, {"market_ts": ts, "open": None, "high": None,
                                   "low": None, "close": None, "buy_volume": None,
                                   "sell_volume": None})
        for k in ("open", "high", "low", "close"):
            if bar[k] is None:
                bar[k] = point.get(k)
        bar["sell_volume"] = point.get("volume")
    out = [b for b in bars.values() if b["close"] is not None]
    out.sort(key=lambda b: b["market_ts"])
    return out


def parse_scalar(body: dict, value_keys: tuple[str, ...]) -> list[dict]:
    return [
        {"market_ts": ts, "value": point[k]}
        for ts, point in series_points(body, None)
        for k in (next((k for k in value_keys if point.get(k) is not None), None),)
        if k is not None
    ]
