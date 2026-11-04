"""Signal engine tests: 9-state thresholds, veto, deterministic grading."""


from signals.engine import decide, grade


def _v(sid, verdict, evidence="e"):
    return {"strategy_id": sid, "strategy_name": sid, "verdict": verdict, "evidence": [evidence]}


def _regime(trend="up", strength="strong"):
    return {
        "trend": {"trend": trend},
        "strength": {"strength": strength},
        "vol": {"vol_regime": "normal"},
    }


def test_strong_buy_requires_regime_confirmation():
    verdicts = [
        _v("mom_trend_cont", "BULLISH"), _v("mom_ema_align", "BULLISH"),
        _v("mom_hh_hl", "BULLISH"), _v("smc_liquidity_sweep", "BULLISH"),
        _v("smc_fvg", "BULLISH"), _v("ict_mss", "BULLISH"),
    ]
    d = decide(verdicts, _regime("up", "strong"), event_veto=False, veto_events=[],
               price=100.0, prev_open_signal=None, plan_levels=None, interval="1h")
    assert d["signal_type"] == "STRONG_BUY"
    assert d["groups_agreeing"] >= 2  # coarse families: momentum + smc


def test_buy_without_regime_confirmation_is_not_strong():
    verdicts = [
        _v("mom_trend_cont", "BULLISH"), _v("mom_breakout_retest", "BULLISH"),
        _v("smc_liquidity_sweep", "BULLISH"), _v("smc_fvg", "BULLISH"),
    ]
    d = decide(verdicts, _regime("sideways", "weak"), event_veto=False, veto_events=[],
               price=100.0, prev_open_signal=None, plan_levels=None, interval="1h")
    assert d["signal_type"] == "BUY"


def test_early_signal_when_momentum_leads_without_cross_group():
    verdicts = [_v("mom_trend_cont", "BULLISH"), _v("mom_expansion", "BULLISH")]
    d = decide(verdicts, _regime("sideways"), event_veto=False, veto_events=[],
               price=100.0, prev_open_signal=None, plan_levels=None, interval="1h")
    assert d["signal_type"] == "EARLY_BUY"
    assert "smaller size" in d["early_rationale"]


def test_wait_when_lean_is_too_weak():
    d = decide([_v("ict_pdh_pdl", "BULLISH")], _regime("sideways"), event_veto=False,
               veto_events=[], price=100.0, prev_open_signal=None, plan_levels=None, interval="1h")
    assert d["signal_type"] == "WAIT"


def test_no_trade_on_nothing():
    d = decide([], _regime("sideways"), event_veto=False, veto_events=[],
               price=100.0, prev_open_signal=None, plan_levels=None, interval="1h")
    assert d["signal_type"] == "NO_TRADE"


def test_event_veto_forces_wait_even_on_big_score():
    verdicts = [_v(f"s{i}", "BULLISH") for i in range(8)]
    d = decide(verdicts, _regime("up", "strong"), event_veto=True,
               veto_events=[{"release": "CPI", "date": "2026-01-02"}],
               price=100.0, prev_open_signal=None, plan_levels=None, interval="1h")
    assert d["signal_type"] == "WAIT"
    assert d["event_veto"] is True


def test_invalidated_breaks_prior_long():
    verdicts = [_v("mom_trend_cont", "BULLISH")]
    prev = {"signal_type": "BUY", "invalidation_level": 105.0}
    d = decide(verdicts, _regime("up"), event_veto=False, veto_events=[],
               price=104.0, prev_open_signal=prev, plan_levels=None, interval="1h")
    assert d["signal_type"] == "INVALIDATED"


def test_grade_stop_wins_pessimistic():
    sig = {"signal_type": "BUY", "price": 100.0,
           "plan": {"stop": 98.0, "t1": 102.0}}
    # one candle touches both stop and target → stop wins
    out = grade(sig, highs_after=[103.0], lows_after=[97.5], closes_after=[101.0])
    assert out["exit_reason"] == "stop+target same bar (pessimistic: stop)"
    assert out["r_multiple"] == -1.0


def test_grade_target_then_expiry():
    sig = {"signal_type": "BUY", "price": 100.0, "plan": {"stop": 98.0, "t1": 102.0}}
    out = grade(sig, highs_after=[101.0, 102.5], lows_after=[99.5, 100.5], closes_after=[101.0, 102.2])
    assert out["exit_reason"] == "target"
    assert out["r_multiple"] == 1.0


def test_grade_direction_only_when_no_plan():
    sig = {"signal_type": "EARLY_BUY", "price": 100.0, "plan": None}
    out = grade(sig, highs_after=[104.0], lows_after=[99.0], closes_after=[103.0])
    assert out["graded"] and out["exit_reason"] == "expiry"
    assert out["direction_move_pct"] == 3.0
    assert out["mfe"] == 4.0 and out["mae"] == 1.0
