"""Strategy framework tests — synthetic candle contexts, no network, no DB."""

from datetime import UTC, datetime, timedelta

from strategies.base import build_context
from strategies.confluence import SweepMssFvgObComposite
from strategies.ict import (
    AsianRangeStrategy,
    FibonacciOTEStrategy,
    MarketStructureShiftStrategy,
)
from strategies.smc import (
    DisplacementStrategy,
    EqualHighsLowsStrategy,
    FairValueGapStrategy,
    LiquiditySweepStrategy,
    OrderBlockStrategy,
    PremiumDiscountStrategy,
)
from strategies.wyckoff import WyckoffSpringStrategy, WyckoffUpthrustStrategy


def _rows(closes, spread=1.0):
    """Synthetic candle rows from a close sequence (high/low = close ± spread)."""
    rows = []
    t0 = datetime(2026, 10, 1, tzinfo=UTC)
    for i, c in enumerate(closes):
        rows.append({
            "market_ts": t0 + timedelta(hours=i),
            "open": closes[i - 1] if i > 0 else c,
            "high": c + spread,
            "low": c - spread,
            "close": c,
            "status": "final",
        })
    return rows


def _ctx(closes, spread=1.0, params=None):
    rows = _rows(closes, spread)
    return build_context("XAUUSD", "1h", rows, rows[-40:], rows[-24:], params=params)


def test_liquidity_sweep_bullish():
    # swing low at 100, then price wicks to 99 and closes back at 100.5
    closes = [100.0, 99.5, 100.5, 100.0, 99.0, 100.0, 100.6, 100.8, 101.0, 101.2,
              100.0, 99.6, 99.0, 100.5, 100.8, 101.0, 101.2, 101.4, 101.6, 101.8]
    dets = LiquiditySweepStrategy().detect(_ctx(closes))
    bullish = [d for d in dets if d.direction == "bullish"]
    assert bullish, "expected a bullish sweep detection"
    assert any("reclaimed: closed above" in e for d in bullish for e in d.evidence)


def test_fvg_detection_and_mitigation():
    # flat warm-up (ATR defined), then gap up: low[i] > high[i-2]
    closes = [100.0] * 20 + [104.0, 108.0, 107.0, 106.0, 105.0, 104.5, 104.0, 103.5, 103.0]
    dets = FairValueGapStrategy().detect(_ctx(closes, spread=0.5))
    bullish = [d for d in dets if d.direction == "bullish"]
    assert bullish
    d = next(d for d in bullish if d.levels["gap_high"] == 107.5)
    assert d.levels["gap_low"] == 100.5
    # later closes fall to 103 -> low 102.5 > 100.5, so this gap stays open
    assert d.status == "active"


def test_order_block_zone_found():
    # swing high at idx 1 (102), drift down, then displacement up breaking 103
    closes = ([100.0, 102.0, 100.0, 99.0, 100.0] * 3
              + [99.5, 110.0, 110.5, 111.0, 111.5, 112.0, 112.5, 113.0, 113.5, 114.0])
    dets = OrderBlockStrategy().detect(_ctx(closes))
    assert dets, "expected order block detection on displacement leg"
    d = [x for x in dets if x.direction == "bullish"][-1]
    assert d.levels["zone_high"] > d.levels["zone_low"]
    assert any("ATR" in e for e in d.evidence)


def test_displacement_flags_large_body():
    closes = [100.0] * 20 + [108.0] + [108.0] * 10  # 8-pt body after ATR warm-up
    dets = DisplacementStrategy().detect(_ctx(closes))
    assert dets and dets[0].direction == "bullish"


def test_mss_requires_displacement():
    closes = [float(i) for i in range(20, 40)] + [38.0]
    dets = MarketStructureShiftStrategy().detect(_ctx(closes))
    # either none or all have displacement evidence
    for d in dets:
        assert any("ATR" in e for e in d.evidence)


def test_composite_bullish_scenario():
    # range -> sweep of the range low with reclaim -> displacement up (MSS)
    closes = ([100.0 + (i % 4) * 0.5 for i in range(30)]   # churn, defines ATR
              + [98.0, 97.0, 100.5]                         # sweep low 96.6 + reclaim close 100.5
              + [103.0, 106.0, 108.0, 110.0]                # displacement up
              + [110.0] * 6)
    ctx = _ctx(closes, spread=0.4)
    dets = SweepMssFvgObComposite().detect(ctx)
    bullish = [d for d in dets if d.direction == "bullish"]
    assert bullish, "expected a bullish composite candidate"
    d = bullish[-1]
    joined = " ".join(d.evidence)
    assert "Liquidity sweep" in joined
    # levels computed in python (targets may need entry+stop; at minimum stop present)
    assert d.levels.get("stop") is not None or any(k.startswith("target_") for k in d.levels)


def test_wyckoff_spring_and_upthrust():
    # range 100-102 for 20 bars, then dip below 100 and reclaim
    closes = [101.0] * 20 + [99.5, 100.5] + [100.8] * 5
    dets = WyckoffSpringStrategy().detect(_ctx(closes, spread=0.3))
    assert dets and dets[-1].direction == "bullish"
    # range then push above 102 and fail
    closes2 = [101.0] * 20 + [102.8, 101.5] + [101.2] * 5
    dets2 = WyckoffUpthrustStrategy().detect(_ctx(closes2, spread=0.3))
    assert dets2 and dets2[-1].direction == "bearish"


def test_premium_discount_zones():
    # zigzag creates confirmed swings: peak 104, trough 100, peak 103
    closes = [100.0, 102.0, 104.0, 102.0, 100.0, 101.5, 103.0, 101.0, 100.5, 100.8]
    closes = closes * 3
    dets = PremiumDiscountStrategy().detect(_ctx(closes))
    assert dets and dets[0].levels["equilibrium"] is not None


def test_fib_ote_zone():
    # bullish impulse 95 -> 120 (swing low idx5, swing high idx26), retrace to 104
    closes = ([100.0 - i for i in range(6)]          # 100 -> 95 (swing low idx5)
              + [95.0 + i for i in range(1, 22)]     # 96 -> 116... up to 116
              )
    # extend to reach 120 then retrace into the OTE zone
    closes += [116.0 + i for i in range(1, 5)]       # 117..120 (swing high)
    closes += [120.0 - i for i in range(1, 17)]      # retrace down to 104
    dets = FibonacciOTEStrategy().detect(_ctx([float(c) for c in closes], spread=0.25))
    bearish = [d for d in dets if d.direction == "bearish"]
    assert bearish
    d = bearish[0]
    # swing high 120.25 / swing low 94.75 -> span 25.5
    # OTE zone hi = 120.25 - 25.5*0.618 = 104.49 ; lo = 120.25 - 25.5*0.79 = 100.11
    assert abs(d.levels["ote_high"] - 104.491) < 0.05
    assert abs(d.levels["ote_low"] - 100.105) < 0.05
    assert d.status == "active"  # price 104 inside zone


def test_eqh_eql_pool():
    closes = [100.0, 102.0, 100.5, 102.05, 101.0] * 4
    dets = EqualHighsLowsStrategy().detect(_ctx(closes))
    eqh = [d for d in dets if "EQH" in " ".join(d.evidence)]
    assert eqh, "expected EQH pool detection"


def test_asian_range_position():
    sessions = {"asia": {"date": "2026-10-01", "high": 101.0, "low": 99.0}}
    closes = [100.0] * 10 + [101.5]
    ctx = _ctx(closes)
    object.__setattr__(ctx, "sessions", sessions)
    dets = AsianRangeStrategy().detect(ctx)
    assert dets and dets[0].direction == "bullish"
