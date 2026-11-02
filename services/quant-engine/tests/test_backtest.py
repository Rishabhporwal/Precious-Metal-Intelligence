"""Backtest tests: metrics math, leakage gate, execution simulation."""

from datetime import UTC, datetime, timedelta

import pytest

from backtesting.engine import run_backtest
from backtesting.leakage import verify_detection_prefix
from backtesting.metrics import compute_metrics
from strategies.base import build_context
from strategies.smc import LiquiditySweepStrategy


def _rows_from(closes, spread=0.4, start_hour=0):
    rows = []
    t0 = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=start_hour)
    for i, c in enumerate(closes):
        rows.append({
            "market_ts": t0 + timedelta(hours=i), "open": closes[i - 1] if i else c,
            "high": c + spread, "low": c - spread, "close": c, "status": "final",
        })
    return rows


def _t(i):
    return datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=i)


def test_metrics_math():
    trades = [
        {"r_multiple": 2.0, "pnl": 20.0, "entry_time": _t(0), "exit_time": _t(3), "exit_price": 1},
        {"r_multiple": -1.0, "pnl": -10.0, "entry_time": _t(5), "exit_time": _t(7), "exit_price": 1},
        {"r_multiple": 1.0, "pnl": 10.0, "entry_time": _t(9), "exit_time": _t(12), "exit_price": 1},
    ]
    m = compute_metrics(trades, initial_equity=1000, risk_per_trade=10)
    assert m["closed_trades"] == 3
    assert m["win_rate"] == pytest.approx(2 / 3, abs=0.001)
    assert m["profit_factor"] == pytest.approx(3.0)
    assert m["expectancy_r"] == pytest.approx(2 / 3, abs=0.001)
    assert m["max_drawdown_pct"] >= 0
    assert m["total_costs"] == 0


def test_leakage_gate_accepts_honest_detection():
    # 60 flat warm-up bars then the sweep pattern — anchor lands after warm-up
    closes = [100.0] * 60
    closes += [100.0, 99.5, 100.5, 100.0, 99.0, 100.0, 100.6, 100.8, 101.0, 101.2,
               100.0, 99.6, 99.0, 100.5, 100.8, 101.0, 101.2, 101.4, 101.6, 101.8]
    rows = _rows_from(closes)
    ctx = build_context("XAUUSD", "1h", rows, rows, rows)
    dets = LiquiditySweepStrategy().detect(ctx)
    assert dets, "expected sweep detection"
    d = dets[0]
    idx = next(i for i, t in enumerate(ctx.times) if t == d.anchor_time)
    assert idx >= 60
    assert verify_detection_prefix("smc_liquidity_sweep", idx, rows, rows, rows) is True


def test_leakage_gate_rejects_short_prefix():
    # anchor inside the first 60 bars -> prefix re-run cannot reproduce (guard)
    closes = [100.0, 99.5, 100.5, 100.0, 99.0, 100.0, 100.6, 100.8, 101.0, 101.2,
              100.0, 99.6, 99.0, 100.5, 100.8, 101.0, 101.2, 101.4, 101.6, 101.8]
    closes = [100.0] * 60 + closes
    rows = _rows_from(closes)
    assert verify_detection_prefix("smc_liquidity_sweep", 10, rows, rows, rows) is False


def _synthetic_backtest_rows():
    closes = [100.0] * 60                              # warm-up (ATR + lookback)
    closes += [100.0 - i * 0.2 for i in range(1, 8)]   # drift down to ~98.6
    closes += [97.0, 96.5, 99.0]                       # sweep low 96.1 + reclaim
    closes += [101.0, 103.0, 105.0, 107.0, 109.0, 111.0, 113.0, 115.0]  # rally
    closes += [115.0] * 30                             # tail
    return _rows_from(closes)


def test_backtest_runs_and_reports():
    rows = _synthetic_backtest_rows()
    result = run_backtest("XAUUSD", "1h", "composite_sweep_mss_fvg_ob", rows=rows,
                          daily=rows[-40:], hourly=rows[-24:], max_wait_bars=40)
    assert "error" not in result
    assert result["detections_found"] >= 0
    assert result["leakage_excluded"] >= 0
    for t in result["trades"]:
        if t["exit_reason"] != "no_fill":
            assert t["exit_reason"] in ("stop", "target", "expired")


def test_backtest_stops_are_pessimistic():
    closes = [100.0] * 60
    closes += [96.0, 96.5, 100.0]      # sweep + reclaim
    closes += [102.0, 90.0]            # brief pop then huge gap-down candle
    closes += [90.0] * 40
    rows = _rows_from(closes)
    result = run_backtest("XAUUSD", "1h", "composite_sweep_mss_fvg_ob", rows=rows,
                          daily=rows[-40:], hourly=rows[-24:], max_wait_bars=40)
    for t in result["trades"]:
        if t["exit_reason"] == "stop":
            assert t["r_multiple"] is None or t["r_multiple"] <= 0.3
