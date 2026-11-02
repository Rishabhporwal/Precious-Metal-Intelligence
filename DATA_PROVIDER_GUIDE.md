# Data Provider Guide

Provider abstraction lives in `services/quant-engine/providers/`:
`base.py` (contracts), `twelve_data.py` (implemented). FRED/CFTC/news/calendar
adapters are reserved for Phase 5.

## Twelve Data (Phase 1 — implemented & verified)

- Env: `TWELVEDATA_API_KEY`
- Rate limiting: token bucket (default 8/min, daily budget 760 under the 800/day cap)
- Retries: exponential backoff on 429/5xx/network errors only; auth and
  entitlement errors fail fast
- Every raw response is archived in `provider_observations` (payload, ok,
  error_message, received_at)
- **Entitlement verification is mandatory**: an instrument is enabled only after
  `POST /v1/instruments/{symbol}/verify` confirms live quote + history against
  the operator's actual subscription.

## Verified entitlements (as of Phase 1, free plan)

| Provider symbol | Available | Used for |
|---|---|---|
| XAU/USD | ✅ | XAUUSD (spot gold) — 5,000 daily candles back to 2007-08-29 |
| SI | ✅ | XAGUSD — **COMEX silver futures**; spot XAG/USD requires Grow/Venture plan |
| XAG/USD | ❌ paywalled | — |
| XAG/GBP | ❌ paywalled | — |

Unverified candidates (EURUSD, USDJPY, DXY, WTI, BRENT, COPPER) stay disabled
until their verify endpoint is run (~2 credits per instrument).

## Credit economy (free plan: 8/min, 800/day)

- ingestion defaults: quotes every 300s per instrument, 1min-candle refresh
  every 900s → 2 instruments ≈ 768/day
- knobs: `QUOTE_POLL_SECONDS`, `MIN_CANDLE_POLL_SECONDS`,
  `TD_RATE_LIMIT_PER_MIN`, `TD_DAILY_BUDGET`

## Volume honesty

Twelve Data volume for spot FX/metals is tick count — the adapter labels it
`volume_type='tick'` and it is never presented as exchange/institutional volume.
Futures symbols carry real traded volume but are still conservatively labeled
`tick` until a verified exchange-volume source is integrated.

## Credentials (all phases)

| Provider    | Env var              | Scope                     | Doc                  |
| ----------- | -------------------- | ------------------------- | -------------------- |
| Twelve Data | `TWELVEDATA_API_KEY` | quotes, OHLC, commodities | twelvedata.com/docs  |
| FRED        | `FRED_API_KEY`       | macro series (Phase 5)    | fred.stlouisfed.org  |
| CFTC        | none (public)        | futures positioning (Ph.5)| cftc.gov             |
