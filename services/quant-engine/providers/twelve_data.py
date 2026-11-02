"""Twelve Data market-data adapter.

Docs: https://twelvedata.com/docs

Behavior:
- sync httpx client with short timeouts
- token-bucket rate limiting (free tier: 8 credits/min, 800/day — configurable)
- retry with exponential backoff on 429/5xx/network errors (rate-limit budget
  respected; never retries 4xx auth/entitlement errors)
- raw provider payloads are returned alongside normalized data so the caller
  can persist provider_observations (spec: preserve raw observations)
"""

import json
import logging
import threading
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

import httpx

from .base import (
    BaseProvider,
    CandleInterval,
    InstrumentVerification,
    NormalizedCandle,
    NormalizedQuote,
    ProviderAuthError,
    ProviderError,
    ProviderUnconfigured,
    RateLimitError,
    SymbolUnavailable,
    VolumeType,
)

logger = logging.getLogger(__name__)

INTERVAL_MAP: dict[CandleInterval, str] = {
    CandleInterval.MIN_1: "1min",
    CandleInterval.MIN_5: "5min",
    CandleInterval.MIN_15: "15min",
    CandleInterval.MIN_30: "30min",
    CandleInterval.HOUR_1: "1h",
    CandleInterval.HOUR_4: "4h",
    CandleInterval.DAY_1: "1day",
    CandleInterval.WEEK_1: "1week",
    CandleInterval.MONTH_1: "1month",
}


class TokenBucket:
    """Thread-safe token bucket for credit-based rate limits."""

    def __init__(self, rate_per_minute: int, daily_budget: int | None = None):
        self.rate_per_minute = rate_per_minute
        self.capacity = max(1, rate_per_minute)
        self.tokens = float(self.capacity)
        self.updated = time.monotonic()
        self.daily_budget = daily_budget
        self.daily_used = 0
        self.daily_date = datetime.now(UTC).date()
        self._lock = threading.Lock()

    def acquire(self, cost: float = 1.0, timeout: float = 60.0) -> None:
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self.updated
                self.tokens = min(self.capacity, self.tokens + elapsed * (self.rate_per_minute / 60.0))
                self.updated = now
                today = datetime.now(UTC).date()
                if today != self.daily_date:
                    self.daily_date = today
                    self.daily_used = 0
                if self.daily_budget is not None and self.daily_used + cost > self.daily_budget:
                    raise RateLimitError("Twelve Data daily credit budget exhausted")
                if self.tokens >= cost:
                    self.tokens -= cost
                    self.daily_used += int(cost)
                    return
                needed = (cost - self.tokens) / (self.rate_per_minute / 60.0)
            if time.monotonic() > deadline:
                raise RateLimitError("Timed out waiting for rate-limit budget")
            time.sleep(min(needed, 1.0))


def _to_decimal(value) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ProviderError(f"Unparseable numeric value from provider: {value!r}") from exc


def _parse_ts(value) -> datetime:
    """Twelve Data datetimes: ISO-8601 strings, sometimes tz-naive (treated as UTC)."""
    if isinstance(value, (int, float)):  # unix seconds
        return datetime.fromtimestamp(float(value), tz=UTC)
    text = str(value).replace(" ", "T")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ProviderError(f"Unparseable timestamp from provider: {value!r}") from exc
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


class TwelveDataProvider(BaseProvider):
    name = "twelvedata"

    def __init__(
        self,
        api_key: str | None,
        base_url: str = "https://api.twelvedata.com",
        requests_per_minute: int = 8,
        daily_budget: int | None = 760,  # headroom under the 800/day free cap
        timeout_s: float = 10.0,
        max_retries: int = 4,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.bucket = TokenBucket(requests_per_minute, daily_budget)
        self.timeout_s = timeout_s
        self.max_retries = max_retries

    # -- internals -----------------------------------------------------------

    def _request(self, endpoint: str, params: dict) -> tuple[dict, int]:
        """Returns (json_body, http_status). Raises after retry budget on transient errors."""
        if not self.api_key:
            raise ProviderUnconfigured(
                "TWELVEDATA_API_KEY is not set — market data cannot be fetched."
            )
        params = {**params, "apikey": self.api_key}
        attempt = 0
        last_error: Exception | None = None
        while attempt <= self.max_retries:
            self.bucket.acquire()
            try:
                resp = httpx.get(
                    f"{self.base_url}/{endpoint}",
                    params=params,
                    timeout=self.timeout_s,
                )
            except httpx.HTTPError as exc:
                last_error = exc
                attempt += 1
                backoff = min(2 ** attempt, 30)
                logger.warning("TwelveData network error (attempt %d): %s — retrying in %ss",
                               attempt, exc, backoff)
                time.sleep(backoff)
                continue

            status = resp.status_code
            if status == 429 or 500 <= status < 600:
                attempt += 1
                backoff = min(2 ** attempt, 30)
                logger.warning("TwelveData HTTP %d (attempt %d) — retrying in %ss", status, attempt, backoff)
                time.sleep(backoff)
                continue

            body = self._decode_json(resp)
            self._raise_on_provider_error(body, status, params.get("symbol", ""))
            return body, status
        raise RateLimitError(f"Twelve Data unavailable after {self.max_retries + 1} attempts: {last_error}")

    @staticmethod
    def _decode_json(resp: httpx.Response) -> dict:
        try:
            return resp.json()
        except json.JSONDecodeError as exc:
            raise ProviderError(f"Twelve Data returned non-JSON (HTTP {resp.status_code})") from exc

    @staticmethod
    def _raise_on_provider_error(body: dict, status: int, symbol: str) -> None:
        # Twelve Data signals errors in-band: {"code": 401|404|429|..., "message": "..."}.
        code = body.get("code")
        message = str(body.get("message", ""))
        if code == 401 or status == 401:
            raise ProviderAuthError(f"Twelve Data rejected the API key: {message}")
        if code == 429:
            raise RateLimitError(f"Twelve Data rate limit: {message}")
        if code == 404 and "not available" in message.lower():
            raise SymbolUnavailable(f"{symbol}: {message}")
        if message and code not in (None, 200):
            raise ProviderError(f"Twelve Data error {code}: {message}")

    # -- public API ----------------------------------------------------------

    def health(self) -> dict:
        return {
            "provider": self.name,
            "credentials_configured": bool(self.api_key),
            "rate_limit_per_minute": self.bucket.rate_per_minute,
            "daily_budget": self.bucket.daily_budget,
            "daily_used": self.bucket.daily_used,
        }

    def fetch_quote(self, provider_symbol: str) -> NormalizedQuote:
        body, _ = self._request("quote", {"symbol": provider_symbol})
        ts = body.get("timestamp") or body.get("datetime")
        price = _to_decimal(body.get("close")) or _to_decimal(body.get("price"))
        if price is None or ts is None:
            raise ProviderError(f"Twelve Data quote for {provider_symbol} missing price/timestamp")
        return NormalizedQuote(
            market_ts=_parse_ts(ts),
            price=price,
            bid=_to_decimal(body.get("bid")),
            ask=_to_decimal(body.get("ask")),
        )

    def fetch_candles(
        self,
        provider_symbol: str,
        interval: CandleInterval,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 5000,
    ) -> list[NormalizedCandle]:
        params: dict = {
            "symbol": provider_symbol,
            "interval": INTERVAL_MAP[interval],
            "outputsize": min(limit, 5000),
            "order": "ASC",
        }
        if start is not None:
            params["startdate"] = start.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")
        if end is not None:
            params["enddate"] = end.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")
        body, _ = self._request("time_series", params)
        values = body.get("values")
        if not isinstance(values, list):
            raise ProviderError(f"Twelve Data time_series returned no values for {provider_symbol}")

        candles: list[NormalizedCandle] = []
        for row in values:
            o, h, l, c = (
                _to_decimal(row.get("open")),
                _to_decimal(row.get("high")),
                _to_decimal(row.get("low")),
                _to_decimal(row.get("close")),
            )
            if o is None or h is None or l is None or c is None:
                raise ProviderError(f"Twelve Data candle missing OHLC: {row!r}")
            volume_raw = row.get("volume")
            # Spot forex/metals have no genuine volume. TD may return tick counts
            # — labeled honestly as tick volume, never as exchange volume.
            volume = _to_decimal(volume_raw) if volume_raw not in (None, "", "0") else None
            candles.append(
                NormalizedCandle(
                    market_ts=_parse_ts(row["datetime"]),
                    open=o, high=h, low=l, close=c,
                    volume=volume,
                    volume_type=VolumeType.TICK if volume is not None else VolumeType.NONE,
                )
            )
        # Contract: ascending by time regardless of provider response order.
        candles.sort(key=lambda c: c.market_ts)
        # The most recent candle may still be forming — provisional; all earlier
        # candles are closed/final. No future information is assumed anywhere.
        provisional = max(candles, key=lambda c: c.market_ts) if candles else None
        return [
            NormalizedCandle(
                market_ts=c.market_ts, open=c.open, high=c.high, low=c.low, close=c.close,
                volume=c.volume, volume_type=c.volume_type,
                status="provisional" if c is provisional else "final",
            )
            for c in candles
        ]

    def verify_instrument(self, provider_symbol: str) -> InstrumentVerification:
        """Live entitlement check. Never assumes availability."""
        if not self.api_key:
            raise ProviderUnconfigured(
                "TWELVEDATA_API_KEY is not set — cannot verify instrument entitlements."
            )
        details: dict = {}
        quote_ok = False
        try:
            quote = self.fetch_quote(provider_symbol)
            quote_ok = True
            details["quote_price"] = str(quote.price)
            details["quote_ts"] = quote.market_ts.isoformat()
        except SymbolUnavailable:
            return InstrumentVerification(
                provider_symbol=provider_symbol, available=False, quote_ok=False, history_ok=False,
                note="symbol not available on this subscription",
            )
        except ProviderError as exc:
            details["quote_error"] = str(exc)

        history_ok = False
        history_from = history_to = None
        try:
            window_start = datetime.now(UTC) - timedelta(days=30)
            candles = self.fetch_candles(
                provider_symbol, CandleInterval.DAY_1, start=window_start, limit=40
            )
            if candles:
                history_ok = True
                history_from = candles[0].market_ts
                history_to = candles[-1].market_ts
                details["history_points"] = len(candles)
        except SymbolUnavailable:
            details["history_error"] = "history not available on this subscription"
        except ProviderError as exc:
            details["history_error"] = str(exc)

        available = quote_ok or history_ok
        note_parts = []
        if not available:
            note_parts.append("no quote and no history available")
        elif not quote_ok:
            note_parts.append("history available but quote endpoint failed")
        elif not history_ok:
            note_parts.append("quote available but history failed")
        else:
            note_parts.append("verified against live API")
        return InstrumentVerification(
            provider_symbol=provider_symbol,
            available=available,
            quote_ok=quote_ok,
            history_ok=history_ok,
            history_from=history_from,
            history_to=history_to,
            note="; ".join(note_parts),
            details=details,
        )
