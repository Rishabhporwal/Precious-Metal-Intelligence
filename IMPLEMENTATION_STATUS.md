# Implementation Status

Last updated: Phase 1 completion.

## Phases

| Phase | Scope                               | Status                 |
| ----- | ----------------------------------- | ---------------------- |
| 0     | Platform bootstrap                  | ✅ complete (verified) |
| 1     | Market data (Twelve Data, backfill) | ✅ complete (verified) |
| 2     | Dashboard                           | ✅ complete (verified) |
| 3     | Technical analysis                  | ✅ complete (verified) |
| 4     | Advanced strategies (SMC/ICT/…)     | ⬜ not started         |
| 5     | Macro & news                        | ⬜ not started         |
| 6     | Quantitative engine                 | ⬜ not started         |
| 7     | AI analyst (LangGraph)              | ⬜ not started         |
| 8     | Trading intelligence, alerts, paper | ⬜ not started         |
| 9     | Backtesting                         | ⬜ not started         |
| 10    | Hardening                           | ⬜ not started         |

## Next implementation tasks (Phase 4)

1. Strategy framework: base.py + registry + engine (deterministic detection records, algo versions)
2. P0 SMC/ICT strategies: Liquidity Sweep, EQH/EQL, BOS/CHoCH/MSS events, FVG, Order Blocks,
   Breaker Blocks, Displacement, Premium/Discount, PDH/PDL, Asian Range, SMT (needs silver —
   decide proxy or defer), Fib/OTE, Failed Breakout, Wyckoff Spring/Upthrust
3. Confluence engine for the first composite: Sweep → MSS → Displacement → FVG → OB
4. Strategy detection persistence (migration 0003) + `/v1/strategies/*` endpoints
5. Chart annotations for detections

## Phase 3 — completed features (verified)

- `indicators/` pure-Python deterministic library: EMA/SMA/RSI(Wilder)/MACD/
  Stochastic/ROC/ATR(Wilder)/ADX(±DI)/Bollinger/HV/RV/vol-percentile + regular
  divergence detection. No-lookahead enforced and **tested** (prefix-invariance).
- `indicators/structure.py`: k-bar confirmation-delayed swings (repaint-free by
  construction), HH/HL/LH/LL labels, S/R clustering with touch counts, BOS/CHoCH
  state machine over confirmed swings + closed candles, PDH/PDL (last completed
  daily), PWH/PWL (ISO weeks, running week skipped), UTC session ranges,
  multi-timeframe EMA-alignment+ADX trend.
- Endpoints: `/v1/instruments/{symbol}/indicators` and `/structure` (quant),
  `/api/v1/markets/{symbol}/indicators|structure` (gateway).
- Dashboard: toggleable EMA 20/50/200 chart overlays + three analytics panels
  (daily momentum, market structure with PDH/PDL/S/R/BOS/CHoCH, MTF trend).

## Phase 3 — verified on live gold data (2026-11-02)

- Daily: RSI 32.7, MACD −12.2, ADX 32.7 with −DI dominant (33.4 vs 16.5) →
  coherent downtrend read; bullish MACD divergences flagged.
- 1H structure: trend UP after **CHoCH bullish @ 3,875.5**; PDH/PDL 3,915.0/3,866.0;
  PWH/PWL 4,082.0/3,871.2; S/R levels clustered with touch counts.
- MTF: 1h sideways-strong (ADX 72), 1day down-strong (ADX 32.7).
- Session ranges flat = Sunday (Nov 1) — correct market reality, not a bug.

## Phase 1 — completed features

- Migration `0002_market_data`: `instruments`, `data_providers`,
  `provider_observations`, `market_quotes`, `market_candles` — `market_candles`
  is a TimescaleDB hypertable whose composite PK doubles as the dedup
  constraint; OHLC-sanity / volume-type / candle-status CHECK constraints.
- Seed script: 8 instruments (XAUUSD, XAGUSD, EURUSD, USDJPY, DXY, WTI, BRENT,
  COPPER) + 5 providers. All instruments start `enabled=false` — nothing is
  ingested until entitlement is **verified against the live API**.
- Twelve Data adapter (`providers/twelve_data.py`): normalized candles/quotes
  (Decimal, UTC), token-bucket rate limiter, exponential-backoff retries on
  429/5xx/network only, honest error mapping (auth/entitlement/rate-limit),
  volume labeled `tick` (never presented as exchange volume), newest candle
  `provisional`, deterministic ascending order.
- Ingestion worker (`python -m ingestion`, own compose service): startup backfill
  (1day + 1h) + quote polling + 1min-candle refresh. Free-plan credit economy:
  ~768 credits/day at defaults (quotes every 5 min, 1min refresh every 15 min,
  2 instruments).
- Quant API `/v1`: instruments list, per-instrument verify / backfill / candles /
  quote, data status.
- Fastify gateway `/api/v1/markets*`: validation + error envelopes, pure proxy.
- Web `/markets` page: live gold/silver price cards with 90-day sparklines,
  per-instrument ingestion table with freshness + verification notes.

## Phase 1 — verified results (live)

| Instrument | Provider symbol | Daily candles | Hourly candles | Note |
|---|---|---|---|---|
| XAUUSD | XAU/USD | 5,000 (from 2007-08-29) | 5,000 | verified, enabled — **sole focus per operator decision** |
| XAGUSD | SI (COMEX futures) | 316 | 2,199 | **parked** (operator decision): spot XAG/USD needs a Grow/Venture plan; candles retained, ingestion disabled |

- Live quote ingested: gold 3,906.34 @ 2026-11-01T20:00Z (refreshed every 5 min).
- Ingestion is gold-only → ~384 Twelve Data credits/day (~52% headroom).
- 6 other instruments stay disabled pending entitlement verification (deliberate).

## Tests executed (Phase 1)

- quant: pytest 14/14 — adapter normalization (ascending order, tick-volume
  labeling, provisional marking), error mapping (401/429/404), retry-on-5xx,
  verify flow; store integration against live TimescaleDB (dedup, correction
  upsert, ordering, OHLC-constraint rejection)
- api: vitest 2/2, tsc clean; ruff clean; Next.js production build clean

## Fixes made during Phase 1 verification

1. TimescaleDB hypertable requires the partition column in every unique index —
   `market_candles` moved from surrogate-id PK to composite PK (also the dedup).
2. psycopg3 rows must be fetched from the cursor returned by `Connection.execute`,
   not the connection (fixed across store/worker/tests).
3. `DATABASE_URL_HOST` precedence centralized in `app/db.py` (host tooling wins;
   containers only set `DATABASE_URL`).
4. Connection pool missing `row_factory=dict_row` (tuples masquerading as dicts).
5. Provider factory extracted from the ingestion worker (API no longer imports
   worker side effects).

## Known issues / limitations

- Web port is **3100** (deliberate deviation: 3000 is used by the operator's other project).
- `scheduler` compose service remains reserved for Phase 5.
- SI history depth limited (~1 year on the free plan).
- Twelve Data credits: polling defaults keep ~92% daily headroom under the 800 cap.

## Phase 2 — completed features (verified results below)

- Dashboard at `/` (gold focus): live price ticker over **WebSocket**
  (`/ws/markets` — Fastify gateway fans out the quant engine's stored quote every
  5s, deduplicated, with auto-reconnect client), TradingView **Lightweight Charts**
  candlestick chart with 9 timeframes (1m→1M) rendering stored candles from
  Postgres, and a **data-freshness panel** (last quote received, market
  timestamp, candle counts, STALE/FRESH badge with 48h threshold).
- Navigation layout across Dashboard / Markets / Status; service status moved to `/status`.
- Gateway: `@fastify/websocket` WS endpoint + CORS allowlist for local origins.
- Zero additional provider credits: charts and WS read stored data only.

## Phase 2 — verified results

- Chart loads 2,000 daily candles client-side from the gateway; timeframe
  switching re-queries the API (no provider calls).
- WS ticker shows live stored price with connection-state indicator (WS LIVE/OFFLINE).
- Production build clean (Turbopack); api vitest 2/2 + tsc clean after the
  `buildApp` async migration (websocket/cors registration).

## Known issues / limitations

- Web port is **3100** (deliberate deviation: 3000 is used by the operator's other project).
- `scheduler` compose service remains reserved for Phase 5.
- Chart annotations (FVG/order blocks/liquidity) arrive with Phase 4 data.
- WebSocket pushes the latest stored quote (poll-and-push, 5s) — true tick
  streaming requires a paid market-data feed and is out of scope for the free plan.

## Next implementation tasks (Phase 3)

1. Indicator engine in the quant service (EMA/RSI/MACD/ATR/BB/ADX/VWAP …)
2. Multi-timeframe trend + market structure (swings, HH/HL, support/resistance, BOS/CHoCH prep)
3. `/v1/instruments/{symbol}/indicators` + `/structure` endpoints
4. Chart overlays for structure (Phase 4 wiring)
