"""Event→market-reaction analysis (enhancement spec §5.1).

For every clustered news event, measure what gold ACTUALLY did around the
event window and compare with the event's gold-impact hypothesis.

Windows (deterministic, UTC, on stored candles):
  pre-window : last_update − 24h → last_update
  post-window: last_update → last_update + 24h (only if fully elapsed)

Reaction verdict:
  confirms     — post-move direction matches the hypothesis (|move| ≥ 0.15%)
  contradicts  — post-move direction opposes the hypothesis (|move| ≥ 0.15%)
  ambiguous    — move < 0.15% (noise threshold)
  pending      — post-window not fully elapsed yet; never graded prematurely
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

WINDOW_HOURS = 24
NOISE_THRESHOLD_PCT = 0.15


def measure_reaction(
    hypothesis: str,
    event_time: datetime,
    candles: list[dict],  # hourly rows ascending: market_ts, close, high, low
    now: datetime | None = None,
) -> dict | None:
    now = now or datetime.now(UTC)
    pre_start = event_time - timedelta(hours=WINDOW_HOURS)
    post_end = event_time + timedelta(hours=WINDOW_HOURS)

    pre = [float(c["close"]) for c in candles if pre_start <= c["market_ts"] <= event_time]
    post = [float(c["close"]) for c in candles if event_time < c["market_ts"] <= post_end]
    post_elapsed = now >= post_end

    if len(pre) < 2 or len(post) < 2:
        return None
    if not post_elapsed:
        return {
            "hypothesis": hypothesis,
            "pre_return_pct": round((pre[-1] - pre[0]) / pre[0] * 100, 3),
            "post_return_pct": None,
            "verdict": "pending",
            "post_end": post_end.isoformat(),
        }

    pre_ret = (pre[-1] - pre[0]) / pre[0] * 100
    post_ret = (post[-1] - post[0]) / post[0] * 100

    if hypothesis not in ("bullish", "bearish") or abs(post_ret) < NOISE_THRESHOLD_PCT:
        verdict = "ambiguous"
    elif (hypothesis == "bullish" and post_ret > 0) or (hypothesis == "bearish" and post_ret < 0):
        verdict = "confirms"
    else:
        verdict = "contradicts"

    return {
        "hypothesis": hypothesis,
        "pre_return_pct": round(pre_ret, 3),
        "post_return_pct": round(post_ret, 3),
        "verdict": verdict,
        "noise_threshold_pct": NOISE_THRESHOLD_PCT,
        "window_hours": WINDOW_HOURS,
    }
