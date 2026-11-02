# Data Provider Guide

Provider abstraction lives in `services/quant-engine/providers/` (Phase 1):
`base.py`, `twelve_data.py`, `fred.py`, `cftc.py`, plus news/calendar adapters
(Phase 5).

## Status (Phase 0)

No adapters implemented yet — Phase 0 is infrastructure only. **No market data
is stored or served, and no mock data exists anywhere in the codebase.**

## Credentials

| Provider    | Env var               | Scope                      | Doc                       |
| ----------- | --------------------- | -------------------------- | ------------------------- |
| Twelve Data | `TWELVEDATA_API_KEY`  | quotes, OHLC, commodities  | twelvedata.com/docs       |
| FRED        | `FRED_API_KEY`        | macro series               | fred.stlouisfed.org       |
| CFTC        | none (public reports) | futures positioning        | cftc.gov                  |

## Instrument enablement policy (Phase 1)

Before an instrument is enabled, its Twelve Data symbol, supported intervals,
historical depth and subscription entitlements are **verified against the live
API** and recorded in `instruments`. Symbols failing verification stay
disabled with a recorded reason. Initial watchlist: XAU/USD, XAG/USD, DXY
(pending symbol validation), EUR/USD, USD/JPY, WTI, Brent, Copper.
