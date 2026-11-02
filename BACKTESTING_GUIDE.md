# Backtesting Guide

Framework lands in Phase 9 (`services/quant-engine/backtesting/`). Rules are
defined now so strategy detection code (Phase 4) is built backtest-compatible.

## Execution assumptions (mandatory)

- Confirmed (closed) candles only; incomplete candles never generate signals.
- Explicit confirmation delay for swing-based patterns (configurable, default ≥1 bar).
- When stop-loss and target are both touched inside one candle, resolution is
  **pessimistic-first** (stop assumed hit) unless the candle's path is unambiguous.
- Spread, slippage and commission modelled per instrument; spread floor from
  observed data, not constants.

## Metrics

Win rate, profit factor, expectancy, max drawdown, average R, Sharpe, Sortino,
average holding period, performance by session, performance by regime.

## Validation discipline

- Walk-forward with out-of-sample segments; no metric reported from in-sample alone.
- No optimizing solely for historical win rate.
- Leakage tests are part of the suite: a strategy fed permuted future data
  must not change past detections (anti-repaint assertion).
- Every run stores: strategy version, parameter hash, data window, cost model,
  random seed (if any) → reproducible.
