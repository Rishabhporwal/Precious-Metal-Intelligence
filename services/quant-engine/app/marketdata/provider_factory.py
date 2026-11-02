"""Provider construction from environment (shared by API and ingestion worker)."""

from __future__ import annotations

import os

from providers.twelve_data import TwelveDataProvider


def load_provider() -> TwelveDataProvider:
    return TwelveDataProvider(
        api_key=os.environ.get("TWELVEDATA_API_KEY") or None,
        requests_per_minute=int(os.environ.get("TD_RATE_LIMIT_PER_MIN", "8")),
        daily_budget=int(os.environ.get("TD_DAILY_BUDGET", "760")),
    )
