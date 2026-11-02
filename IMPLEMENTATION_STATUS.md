# Implementation Status

Last updated: Phase 1 completion.

## Phases

| Phase | Scope                               | Status                 |
| ----- | ----------------------------------- | ---------------------- |
| 0     | Platform bootstrap                  | ✅ complete (verified) |
| 1     | Market data (Twelve Data, backfill) | ✅ complete (verified) |
| 2     | Dashboard                           | ✅ complete (verified) |
| 3     | Technical analysis                  | ✅ complete (verified) |
| 4     | Advanced strategies (SMC/ICT/…)     | ✅ complete (verified) |
| 5     | Macro & news                        | ✅ complete (verified) |
| 6     | Quantitative engine                 | ✅ complete (verified) |
| 7     | AI analyst (LangGraph)              | ✅ complete (verified) |
| 8     | Trading intelligence, alerts, paper| ✅ complete (verified) |
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

## Next implementation tasks (Phase 5)

1. FRED adapter (macro series: DXY components, yields, CPI/PCE/NFP)
2. Economic calendar source + `economic_events` migration
3. CFTC positioning reports adapter
4. News ingestion + classification (LLM, untrusted-input hardened)
5. `scheduler` compose service (calendar/news polling)

## Phase 4 — completed features (verified)

- Strategy framework: `strategies/base.py` (Detection record + CandleContext with
  ATR/swings/structure events/prev-day-week/session data), `registry.py` (16 P0
  strategies), `engine.py` (run + append-only persistence, unique-constraint
  dedup, per-strategy enable/params from `strategy_configs`).
- 16 P0 strategies implemented and tested: Liquidity Sweep (multi-bar reclaim,
  ATR-filtered), EQH/EQL pools, FVG (fill tracking → active/consumed), Order
  Blocks (displacement-confirmed, mitigation tracked), Breaker Blocks,
  Displacement, Premium/Discount, PDH/PDL/PWH/PWL liquidity, Asian Range,
  MSS (CHoCH + displacement), Fib/OTE (impulse-leg semantics), Failed Breakout,
  Wyckoff Spring/Upthrust (price-only, no phase claims), SMT (gold vs counterpart
  on stored candles), and the **composite** Sweep→MSS→Displacement→FVG→OB with
  satisfied/missing/conflicting conditions + Python-computed entry/stop/R-targets.
- Migration 0004: `strategy_detections` (append-only, identity-deduped),
  `strategy_configs`, `market_structure_events`.
- Ingestion auto-evaluates strategies after candle writes (never blocks ingestion).
- Endpoints: `/api/v1/strategies{,/detections,/evaluate}`; `/strategies` UI with
  registry, detections table, active-level chart annotations.

## Phase 4 — verified on live gold data (2026-11-02)

- 16/16 strategies registered & enabled; evaluation over 1h+1day produced
  **103 persisted detections** (57 1h + 46 1day), e.g. active bullish FVG
  3,876.1–3,894.7, failed-breakout reclaim @ 3,875.5, 1h displacements both
  directions, OTE zones around 3,906–3,910.
- Re-running evaluation persists 0 new rows (identity dedup verified).
- Composite candidates carry entry/stop/target levels computed in Python; marked
  `complete` only when all five conditions satisfied — never a trade signal.

## Next implementation tasks (Phase 6)

1. Correlation engine (gold vs yields/DXY/oil on stored daily candles)
2. Regime detection (deterministic first: vol-percentile + trend state)
3. Historical scenario comparison (e.g., "current RSI/vol regime vs history")
4. Scenario generation feed for the Phase 7 AI analyst

## Next implementation tasks (Phase 7)

1. LLM provider integration (OpenRouter, per platform convention — verify model slug against GET /api/v1/models)
2. LangGraph analyst graph: Technical / SMC-ICT / Macro / News / Quant / Risk nodes → Chief synthesis
3. Structured outputs (Pydantic-validated JSON) + prompt/model version tracking
4. Evidence reconciliation: scenarios + detections + macro + quant stats as evidence; LLM never emits numbers
5. Analysis persistence (market_analyses + analysis_evidence migrations) + `/api/v1/analysis/*`
6. News sentiment classification (fills `classified`/`sentiment` honestly)

## Next implementation tasks (Phase 8)

1. Contract specs per instrument + position sizing (1% risk rule, $1k capital context)
2. Trade setup validation gate (stale data / invalid stop / min R-R / event-risk policy)
3. Alert engine (price/structure/setup alerts, dedupe + cooldowns) + Telegram
4. Paper trading engine (virtual accounts, fills, P&L) + migrations
5. `/api/v1/setups` + `/api/v1/paper/*` endpoints + UI

## Next implementation tasks (Phase 9)

1. Backtest engine core: historical replay of composite strategy with cost model
2. Metrics (win rate, PF, expectancy, max DD, avg R, Sharpe/Sortino, by session)
3. Walk-forward + out-of-sample split
4. Leakage tests (anti-repaint assertion on strategies)
5. `/api/v1/backtests` + results UI

## Phase 8 — completed features (verified)

- **Risk engine** (`app/risk.py`): setup construction from composite detections;
  validation gate = fresh quote (≤15 min), entry-not-missed, stop ≥ 0.3 ATR with
  correct side, R/R ≥ 1.5, **48h high-impact event policy**; risk-based sizing on
  the operator's real context ($1,000 equity, 1% risk, per-oz contract spec).
- **Alert engine** (`app/alerts.py` + `providers/telegram.py`): 7 rule kinds
  (price bands, sweep, FVG, MSS, setup, analysis), cooldown + dedupe (a
  continuously-true condition fires once per window), Telegram delivery with
  honest `delivered=false + error` when unconfigured.
- **Paper trading** (`app/paper.py`): $1,000 default account, market fills at
  stored quotes, **pessimistic stop fills**, SL/TP monitoring (scheduler, 2 min),
  trade outcomes linked back to setups (R-multiple), performance stats.
  Simulated only — no live broker code exists anywhere.
- Migration 0007: trade_setups, trade_outcomes, alert_rules, alert_events,
  paper_accounts, paper_trades, paper_trade_fills.
- UI: `/setups` (validated + transparently-rejected setups with reasons),
  `/paper` (equity/P&L cards, trade form with risk-based sizing, open/closed
  tables), `/alerts` (rule CRUD, browser notifications, event history).

## Phase 8 — verified live (2026-11-02)

- Risk gate correctly **rejected** the active composite candidate with reasons:
  "stop too tight (10.10 < 0.3 ATR = 16.63)", "R/R 1.00 below minimum 1.5" —
  the gate working as designed, not a failure.
- Alert fired: price 3,911.85 ≥ 3,800 rule → event recorded with
  `delivered=false, error=TELEGRAM not configured` (honest).
- Paper trade: risk-based sizing **0.0894 oz** = $10 ÷ $111.85 stop distance
  (1% rule exact), filled at 3,911.85, closed, outcome linked.

## Phase 7 — completed features (verified)

- **LLM**: OpenRouter `deepseek/deepseek-chat` (chosen from 452 live models:
  $0.26/M in, $1.03/M out; slug verified with a live call). **Redis response
  cache** (12h TTL, HIT/MISS logged) + DB evidence-hash dedupe — verified:
  identical prompt = cache HIT with zero spend; identical evidence = analysis
  reused with zero LLM call.
- **LangGraph**: snapshot → fan-out gatherers (technical / strategies / macro /
  quant — all deterministic Python) → risk node (deterministic: ATR reference
  stop distance, 48h high-impact event warnings, quote staleness) → **single
  cached LLM synthesis** → validation → persist. Retry capped at 1.
- **Number-containment guarantee**: every numeric literal in the LLM narrative
  must exist in the evidence pack (tight tolerance; indicator-name numbers
  stripped; small-int allowlist for counts/horizons). Violations → retry with
  violation feedback → deterministic fallback flagged `deterministic_fallback`.
- Migration 0006: `market_analyses` (append-only, model/prompt/evidence-hash
  tracked) + `analysis_evidence`.
- News classification: one batched cached call; conservative labels only.
- Scheduler: analysis + classification every 12h.
- UI `/analyst`: scenario cards (bullish/neutral/bearish) with evidence-key
  citations, risk constraints, generate button.

## Phase 7 — verified live (2026-11-02)

- Validated LLM analysis persisted (status `llm`): 3 scenarios citing evidence
  keys (choch_bullish, wyckoff_spring, COT net longs, declining DGS10/DFII10)
  with only evidence-contained levels (3,915.02 / 3,875.53 / 3,866.02).
- Cache HIT verified (call 2 = zero spend). News classification ran (4 articles).
- Total LLM spend across all Phase 7 testing: **≈ $0.012**. Steady-state
  projection: ~$0.01/day (analysis + classification at 12h cadence).
- Real bugs fixed during verification: FastAPI `Query` default leaked into
  direct route-function calls (graph gather node); LangGraph retry routing
  (retry_count incremented before router check → never retried); status
  varchar(16) too short for `deterministic_fallback`.

## Phase 6 — completed features (verified)

- `quant/correlations.py`: as-of join with 7-day staleness guard, **pairwise**
  return alignment, rolling 30d correlation + full-sample Pearson. Live values:
  gold vs broad USD **−0.21** (classic inverse), vs 10Y yield **+0.30**, vs real
  yield +0.25, vs WTI +0.07.
- `quant/regimes.py`: deterministic regime = EMA alignment × HV percentile ×
  ADX strength → live: **"down trend / low vol / strong"**.
- `quant/scenarios.py`: empirical forward-return statistics per RSI×vol bucket
  (5/10/20d horizons, median/mean/up-rate/**n**) — explicitly labeled as
  historical frequencies, not predictions. Live bucket (neutral/low-vol):
  n≈1,090, 20d median +0.74% vs all-time +0.61%.
- Gold/silver correlation: near-zero (0.00) with the free-plan SI feed —
  **surfaced with a data-quality caveat** rather than hidden.
- Endpoint `/v1/instruments/{symbol}/quant` → gateway → dashboard Quant panel.

## Phase 5 — completed features (verified)

- **FRED adapter** (`providers/fred.py`): 9-series watchlist — 2Y/10Y nominal
  yields, 10Y real yield (DFII10), broad trade-weighted USD index (DTWEXBGS,
  honest DXY proxy — DXY itself is proprietary ICE data), CPI, PCE, nonfarm
  payrolls, unemployment, WTI spot. Observations stored **append-only with
  fetch vintage** (`macro_observations`). Auth errors surfaced honestly.
- **CFTC adapter** (`providers/cftc.py`): public Socrata futures-only COT —
  gold & silver net non-commercial positioning with full detail JSON.
- **Economic calendar**: real scheduled release dates from FRED's release API
  (no extra provider) — CPI/NFP/PCE tracked, past + upcoming.
- **News ingestion** (`providers/news_rss.py`): multi-feed RSS parser; HTML
  stripped (untrusted input → plain text only); `classified=false` until the
  Phase 7 LLM — no sentiment invented.
- **Scheduler service**: macro 6h, calendar+CFTC 12h, news 30min polling loops.
- Endpoints `/api/v1/macro/{summary,events,news}`; `/macro` UI page (series
  cards with deltas, CFTC positioning, calendar, news list).

## Phase 5 — verified live (2026-11-02)

- First scheduler cycle: **126 FRED observations**, 18 release dates, 16 CFTC
  rows, 51 articles (47 new after dedup) — all stored.
- Live values: 10Y 4.98% (−0.07), 2Y 4.61%, real yield 2.63%, broad USD 121.3,
  WTI $103.37, CPI 336.3, UNRATE 4.2%.
- CFTC: gold net non-commercial **+186,451** contracts (54.7% long of OI),
  silver +19,703 — report date 2026-10-27.
- Calendar: NFP 2026-11-06, CPI 2026-11-10, PCE 2026-11-25 (upcoming, real).
- Caught by own UI: quant container reported FRED unconfigured (key was only in
  scheduler env) — fixed by passing the key to the quant service; health now
  truthfully reports configured.

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
