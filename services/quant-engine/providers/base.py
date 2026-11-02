"""Provider abstraction layer.

Every market-data provider implements BaseProvider. Normalized models use
UTC-aware timestamps and Decimal prices. No provider may fabricate data:
missing credentials raise ProviderUnconfigured and callers surface honest
status, never mock fallbacks.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum


class CandleInterval(str, Enum):
    MIN_1 = "1min"
    MIN_5 = "5min"
    MIN_15 = "15min"
    MIN_30 = "30min"
    HOUR_1 = "1h"
    HOUR_4 = "4h"
    DAY_1 = "1day"
    WEEK_1 = "1week"
    MONTH_1 = "1month"


class VolumeType(str, Enum):
    NONE = "none"
    TICK = "tick"
    BASE = "base"
    EXCHANGE = "exchange"


class ProviderError(Exception):
    """Base class for provider failures."""


class ProviderUnconfigured(ProviderError):
    """Credentials missing — integration reports status, never fakes data."""


class ProviderAuthError(ProviderError):
    """API key rejected."""


class RateLimitError(ProviderError):
    """Provider rate limit exhausted after retries."""


class SymbolUnavailable(ProviderError):
    """Symbol not entitled / not available on this subscription."""


@dataclass(frozen=True)
class NormalizedCandle:
    market_ts: datetime  # UTC-aware
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None = None
    volume_type: VolumeType = VolumeType.NONE
    status: str = "final"  # final | provisional (last in-progress candle)


@dataclass(frozen=True)
class NormalizedQuote:
    market_ts: datetime  # UTC-aware
    price: Decimal
    bid: Decimal | None = None
    ask: Decimal | None = None


@dataclass(frozen=True)
class InstrumentVerification:
    provider_symbol: str
    available: bool
    quote_ok: bool
    history_ok: bool
    history_from: datetime | None = None
    history_to: datetime | None = None
    note: str = ""
    details: dict = field(default_factory=dict)


class BaseProvider(ABC):
    name: str

    @abstractmethod
    def health(self) -> dict:
        """Provider reachability + credential status. Honest, no fabrication."""

    @abstractmethod
    def fetch_quote(self, provider_symbol: str) -> NormalizedQuote:
        ...

    @abstractmethod
    def fetch_candles(
        self,
        provider_symbol: str,
        interval: CandleInterval,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 5000,
    ) -> list[NormalizedCandle]:
        """Ascending-by-time candles. Confirmed candles carry status='final'."""

    @abstractmethod
    def verify_instrument(self, provider_symbol: str) -> InstrumentVerification:
        """Live entitlement check: symbol exists, quote works, history depth."""
