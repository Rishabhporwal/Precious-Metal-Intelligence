# Strategy Definitions

Authoritative definitions for every implemented strategy: exact detection
conditions, confirmation rules, tolerances, invalidation, and algorithm
version. **Nothing is implemented yet (Phase 0).**

## Priority order (from master spec)

- **P0 (first to build, Phase 4):** Liquidity Sweep, EQH/EQL, BOS, CHoCH, MSS,
  FVG, Order Blocks, Breaker Blocks, Displacement, Premium/Discount,
  Previous Day/Week High/Low, Asian Range Liquidity, SMT (Gold/Silver),
  Fibonacci/OTE, Failed Breakout, Wyckoff Spring/Upthrust.
- **P1:** ICT session models, Power of Three, Judas Swing, Silver Bullet, IFVG,
  Mitigation Blocks, Anchored VWAP, Volume Profile, CVD (data permitting),
  advanced Wyckoff.
- **P2:** Footprint, DOM, Absorption, advanced order flow, statistical regimes.

## First composite strategy (Phase 4 acceptance target)

Liquidity Sweep → MSS/CHoCH (closed candle) → Displacement → FVG → Order Block
overlap → retracement entry zone → ATR-anchored stop → scaled targets → R/R
validation. Full deterministic rules will be written here before code, with
the inverse (bearish) mirror.

## Standing rules

- Deterministic, repainting-free, no future-candle leakage; confirmed candles only.
- A detection ≠ a trade recommendation — confluence, confirmation and risk
  validation are separate gates.
- Order-flow features stay disabled until real trade/order-book data exists;
  OHLC-derived "order flow" is prohibited (fabrication).
