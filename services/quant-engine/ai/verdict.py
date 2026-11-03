"""Daily Verdict engine — the product's single deliverable.

Fuses every signal source the platform already produces into ONE call:
  direction (bullish / bearish / neutral) + confidence
  + an actionable plan: entry zone, stop-loss, T1, T2, key support/resistance
  + drivers (which evidence contributed, with plain-English labels)
  + invalidations (what would flip the call)

HARD RULE (spec §24.10-11): every number is computed here, deterministically,
from stored candles + strategy detections + macro/news records. The LLM may
only narrate the reasoning — it receives the computed plan and is forbidden
from producing levels. If the LLM is unavailable, the deterministic verdict
still ships with a template narrative.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from indicators.oscillators import atr
from indicators.structure import full_structure_report

# direction vote weights
W_TREND_DAILY = 2.0
W_TREND_H1 = 1.0
W_STRATEGY_BIAS = 1.0
W_NEWS = 0.5


def _atr_from_daily(daily: list[dict]) -> float | None:
    highs = [float(r["high"]) for r in daily[-20:]]
    lows = [float(r["low"]) for r in daily[-20:]]
    closes = [float(r["close"]) for r in daily[-20:]]
    if len(closes) < 15:
        return None
    vals = [v for v in atr(highs, lows, closes, 14) if v is not None]
    return vals[-1] if vals else None


def _direction_score(
    trend_daily: str,
    trend_hourly: str,
    strategy_bias: dict,
    news_net: int | None,
) -> tuple[float, list[dict]]:
    """Weighted votes -> score in roughly [-4.5, +4.5]. Positive = bullish."""
    score = 0.0
    drivers: list[dict] = []

    if trend_daily in ("up", "down"):
        v = W_TREND_DAILY if trend_daily == "up" else -W_TREND_DAILY
        score += v
        drivers.append({
            "source": "technical",
            "label": f"Daily trend is {trend_daily}",
            "plain": f"The daily chart trend is {trend_daily}.",
            "vote": v,
        })
    if trend_hourly in ("up", "down"):
        v = W_TREND_H1 if trend_hourly == "up" else -W_TREND_H1
        score += v
        drivers.append({
            "source": "technical",
            "label": f"1H trend is {trend_hourly}",
            "plain": f"The hourly chart trend is {trend_hourly}.",
            "vote": v,
        })

    b = int(strategy_bias.get("net", 0))
    if b:
        v = W_STRATEGY_BIAS if b > 0 else -W_STRATEGY_BIAS
        score += v
        n_bull = strategy_bias.get("bullish", 0)
        n_bear = strategy_bias.get("bearish", 0)
        drivers.append({
            "source": "strategies",
            "label": f"Pattern signals: {n_bull} bullish vs {n_bear} bearish (48h)",
            "plain": f"Our pattern detectors fired {n_bull} bullish and {n_bear} bearish signals in the last 48 hours.",
            "vote": v,
        })

    if news_net is not None and abs(news_net) >= 1:
        v = W_NEWS if news_net > 0 else -W_NEWS
        score += v
        drivers.append({
            "source": "news",
            "label": f"News sentiment net {news_net:+d}",
            "plain": f"Recent headlines lean {'positive' if news_net > 0 else 'negative'} for gold.",
            "vote": v,
        })
    return round(score, 2), drivers


def _confidence(score: float, n_drivers: int, veto: bool) -> str:
    if veto:
        return "low"
    if abs(score) >= 3 and n_drivers >= 3:
        return "high"
    if abs(score) >= 1.5:
        return "medium"
    return "low"


def _levels_from_structure(
    price: float,
    sr: dict,
    pdh: float | None,
    pdl: float | None,
    atr_val: float | None,
    direction: str,
) -> dict:
    """Deterministic plan levels. Stop = structure side with an ATR floor; targets = R multiples."""
    supports = sorted((float(s["price"]) for s in sr.get("supports", [])), reverse=True)
    resistances = sorted(float(r["price"]) for r in sr.get("resistances", []))
    a = atr_val or max(price * 0.006, 5.0)  # conservative fallback

    if direction == "bullish":
        entry_candidates = [s for s in supports if s < price]
        entry_low = entry_candidates[0] if entry_candidates else price - 0.5 * a
        entry_high = min(entry_low + 0.35 * a, price)
        stop = min(entry_low - 0.8 * a, (pdl or entry_low) - 0.2 * a)
        risk = entry_high - stop
        t1, t2 = entry_high + risk, entry_high + 2 * risk
    else:
        entry_candidates = [r for r in resistances if r > price]
        entry_high = entry_candidates[0] if entry_candidates else price + 0.5 * a
        entry_low = max(entry_high - 0.35 * a, price)
        stop = max(entry_high + 0.8 * a, (pdh or entry_high) + 0.2 * a)
        risk = stop - entry_low
        t1, t2 = entry_low - risk, entry_low - 2 * risk

    key_supports = [s for s in supports if s < price][:3]
    key_resistances = [r for r in resistances if r > price][:3]
    if pdl and pdl < price and pdl not in key_supports:
        key_supports.append(pdl)
    if pdh and pdh > price and pdh not in key_resistances:
        key_resistances.insert(0, pdh)

    return {
        "entry_low": round(entry_low, 2),
        "entry_high": round(entry_high, 2),
        "stop": round(stop, 2),
        "t1": round(t1, 2),
        "t2": round(t2, 2),
        "risk_per_oz": round(abs(entry_high - stop), 2),
        "supports": [round(s, 2) for s in sorted(set(key_supports), reverse=True)],
        "resistances": [round(r, 2) for r in sorted(set(key_resistances))],
        "atr14": round(a, 2),
    }


def build_verdict(
    symbol: str,
    quote_price: float | None,
    daily: list[dict],
    hourly: list[dict],
    strategy_bias: dict,
    events: list[dict],
    news_net: int | None,
) -> dict:
    now = datetime.now(UTC)
    if quote_price is None:
        return {"error": "no live quote — cannot compute a verdict without current price"}

    closes = [float(r["close"]) for r in daily]
    highs = [float(r["high"]) for r in daily]
    lows = [float(r["low"]) for r in daily]
    h_closes = [float(r["close"]) for r in hourly]
    report = full_structure_report(highs, lows, closes, daily, hourly)

    # multi-timeframe trend: reuse structure trend for daily-swing view, plus a
    # simple hourly EMA alignment for the short side
    trend_daily = report.trend
    trend_hourly = report.trend  # refined below
    if len(h_closes) >= 30:
        def _ema(vals: list[float], n: int) -> float | None:
            k = 2 / (n + 1)
            e = vals[0]
            for v in vals[1:]:
                e = v * k + e * (1 - k)
            return e
        e20, e50 = _ema(h_closes, 20), _ema(h_closes, 50)
        if e20 and e50:
            trend_hourly = "up" if e20 > e50 * 1.0005 else "down" if e20 < e50 * 0.9995 else "sideways"

    score, drivers = _direction_score(trend_daily, trend_hourly, strategy_bias, news_net)

    # Event veto: high-impact release inside 48h -> stand aside, no directional plan.
    # economic_events has no impact column — classify by release name (deterministic).
    HIGH_IMPACT = ("cpi", "nonfarm", "non-farm", "nfp", "fomc", "federal funds",
                   "pce", "unemployment", "payroll", "interest rate")
    veto_events = []
    today = now.date()
    for e in events:
        name = (e.get("release_name") or "").lower()
        if not any(p in name for p in HIGH_IMPACT):
            continue
        try:
            raw_date = e["event_date"]
            d = raw_date if isinstance(raw_date, datetime) else datetime.fromisoformat(str(raw_date).replace("Z", "+00:00"))
            d_date = d.date() if isinstance(d, datetime) else d
        except ValueError:
            continue
        if today <= d_date <= today + timedelta(days=2):
            veto_events.append(e)
    veto = bool(veto_events)

    if veto:
        direction = "neutral"
    elif score >= 1.5:
        direction = "bullish"
    elif score <= -1.5:
        direction = "bearish"
    else:
        direction = "neutral"

    confidence = _confidence(score, len(drivers), veto)
    atr_val = _atr_from_daily(daily)

    plan = None
    if direction != "neutral":
        plan = _levels_from_structure(quote_price, {
            "supports": report.supports,
            "resistances": report.resistances,
        }, report.pdh, report.pdl, atr_val, direction)

    invalidations: list[str] = []
    if plan:
        invalidations.append(
            f"If gold closes beyond ${plan['stop']:,.0f} against this call, the view is wrong — the plan is void."
        )
    if veto_events:
        invalidations.append(
            "A high-impact release is due within 48h ("
            + ", ".join(e["release_name"] for e in veto_events[:3])
            + ") — expect violent moves either way; the plan stands down until it passes."
        )
    invalidations.append("If the trend flips against this call, the verdict is stale — refresh before acting.")

    return {
        "symbol": symbol,
        "as_of": now.isoformat(),
        "price": quote_price,
        "direction": direction,
        "confidence": confidence,
        "score": score,
        "drivers": drivers,
        "trend_daily": trend_daily,
        "trend_hourly": trend_hourly,
        "event_risk": {
            "veto": veto,
            "events": [{"release": e["release_name"], "date": str(e["event_date"])} for e in veto_events],
        },
        "plan": plan,
        "invalidations": invalidations,
        "key_levels": {
            "supports": [round(float(s["price"]), 2) for s in report.supports][:3],
            "resistances": [round(float(r["price"]), 2) for r in report.resistances][:3],
            "prev_day_high": round(report.pdh, 2) if report.pdh else None,
            "prev_day_low": round(report.pdl, 2) if report.pdl else None,
            "prev_week_high": round(report.pwh, 2) if report.pwh else None,
            "prev_week_low": round(report.pwl, 2) if report.pwl else None,
        },
        "method": "deterministic weighted votes; levels from stored structure + ATR; LLM narrates only",
    }
