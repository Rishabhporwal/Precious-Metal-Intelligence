"""OpenMarket Data API client (https://openmarket.xyz — public, documented
API, free tier: 10 weight/min / 1000 weight/day / 7-day history).

Crypto-only: BTC/ETH/SOL per-side trade candles (aggressive buys vs sells),
open interest, funding rates and liquidations. The key lives in
OPENMARKET_API_KEY; without it everything degrades honestly (no data, no
fabrication).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import httpx

BASE_URL = "https://api.openmarket.xyz/v1/points"
EXCHANGE = "BINANCE_FUTURES"  # single venue keeps every query at 1x weight
SYMBOLS = ("BTC", "ETH", "SOL")

CANDLES = "TRADE_AGG"  # per-side: aggressive buys vs sells
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
) -> list[dict]:
    """One API call; returns the raw point list. 1x weight for all v1 types."""
    now = int(datetime.now(UTC).timestamp())
    params = {
        "type": data_type,
        "exchange": EXCHANGE,
        "rawSymbol": f"{coin}USDT",
        "interval": interval,
        "from": now - lookback_seconds,
        "period": 3600,
    }
    r = httpx.get(BASE_URL, params=params, headers={"X-OpenMarket-Key": api_key()}, timeout=timeout)
    r.raise_for_status()
    body = r.json()
    # the docs don't fix a response envelope — accept the common shapes
    if isinstance(body, list):
        return body
    for key in ("points", "data", "results", "values"):
        if isinstance(body.get(key), list):
            return body[key]
    return []


def _num(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_candles(points: list[dict]) -> list[dict]:
    """Normalize per-side candles; shape-tolerant (time/openTime/ts fields)."""
    out = []
    for p in points:
        ts = p.get("time") or p.get("t") or p.get("openTime") or p.get("ts") or p.get("timestamp")
        if ts is None:
            continue
        ts = int(ts)
        if ts > 1e12:  # ms → s
            ts //= 1000
        out.append(
            {
                "market_ts": datetime.fromtimestamp(ts, tz=UTC),
                "open": _num(p.get("open") or p.get("o")),
                "high": _num(p.get("high") or p.get("h")),
                "low": _num(p.get("low") or p.get("l")),
                "close": _num(p.get("close") or p.get("c")),
                "buy_volume": _num(p.get("buyVolume") or p.get("buy_volume") or p.get("buyVol") or p.get("buy")),
                "sell_volume": _num(p.get("sellVolume") or p.get("sell_volume") or p.get("sellVol") or p.get("sell")),
            }
        )
    out = [b for b in out if b["open"] is not None and b["close"] is not None]
    out.sort(key=lambda b: b["market_ts"])
    return out


def parse_scalar(points: list[dict], value_keys: tuple[str, ...]) -> list[dict]:
    out = []
    for p in points:
        ts = p.get("time") or p.get("t") or p.get("ts") or p.get("timestamp")
        if ts is None:
            continue
        ts = int(ts)
        if ts > 1e12:
            ts //= 1000
        value = None
        for k in value_keys:
            if p.get(k) is not None:
                value = _num(p.get(k))
                break
        if value is None:
            continue
        out.append({"market_ts": datetime.fromtimestamp(ts, tz=UTC), "value": value})
    out.sort(key=lambda b: b["market_ts"])
    return out
