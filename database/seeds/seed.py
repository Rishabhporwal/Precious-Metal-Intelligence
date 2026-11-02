"""Seed the instrument registry and data provider registry.

Idempotent upserts. Instruments start enabled=false and
entitlement_verified=false — the Twelve Data verification step
(`POST /v1/instruments/{symbol}/verify`) flips both based on live API
entitlement checks, never on assumptions.

Run: uv run python ../../database/seeds/seed.py   (from services/quant-engine)
"""

import os
import sys

import psycopg

INSTRUMENTS = [
    # symbol, name, asset_class, base, quote, candidate provider symbol
    ("XAUUSD", "Gold Spot (XAU/USD)", "metal", "XAU", "USD", "XAU/USD"),
    ("XAGUSD", "Silver Spot (XAG/USD)", "metal", "XAG", "USD", "XAG/USD"),
    ("EURUSD", "Euro / US Dollar", "fx", "EUR", "USD", "EUR/USD"),
    ("USDJPY", "US Dollar / Japanese Yen", "fx", "USD", "JPY", "USD/JPY"),
    ("DXY", "US Dollar Index", "index", "USD", None, None),  # symbol availability must be verified
    ("WTI", "WTI Crude Oil", "energy", "WTI", "USD", None),  # candidate symbols verified against provider
    ("BRENT", "Brent Crude Oil", "energy", "BRENT", "USD", None),
    ("COPPER", "Copper", "metal", "XCU", "USD", None),
]

PROVIDERS = [
    # name, kind, base_url
    ("twelvedata", "market", "https://api.twelvedata.com"),
    ("fred", "macro", "https://api.stlouisfed.org"),
    ("cftc", "positioning", "https://publicreporting.cftc.gov"),
    ("economic_calendar", "calendar", None),
    ("news", "news", None),
]


def main() -> None:
    url = os.environ.get("DATABASE_URL_HOST") or os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL_HOST or DATABASE_URL must be set", file=sys.stderr)
        sys.exit(1)

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            for name, kind, base_url in PROVIDERS:
                cur.execute(
                    """
                    INSERT INTO data_providers (name, kind, base_url)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (name) DO UPDATE
                        SET kind = EXCLUDED.kind, base_url = EXCLUDED.base_url
                    """,
                    (name, kind, base_url),
                )

            cur.execute("SELECT id FROM data_providers WHERE name = 'twelvedata'")
            td_id = cur.fetchone()[0]

            for symbol, name, asset_class, base, quote, provider_symbol in INSTRUMENTS:
                cur.execute(
                    """
                    INSERT INTO instruments
                        (symbol, name, asset_class, base_ccy, quote_ccy,
                         provider_symbol, provider_id, enabled, entitlement_verified)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, false, false)
                    ON CONFLICT (symbol) DO UPDATE
                        SET name = EXCLUDED.name,
                            asset_class = EXCLUDED.asset_class,
                            base_ccy = EXCLUDED.base_ccy,
                            quote_ccy = EXCLUDED.quote_ccy,
                            provider_symbol = COALESCE(instruments.provider_symbol, EXCLUDED.provider_symbol),
                            provider_id = COALESCE(instruments.provider_id, EXCLUDED.provider_id)
                    """,
                    (symbol, name, asset_class, base, quote, provider_symbol, td_id),
                )
        conn.commit()
    print(f"Seeded {len(INSTRUMENTS)} instruments and {len(PROVIDERS)} providers.")


if __name__ == "__main__":
    main()
