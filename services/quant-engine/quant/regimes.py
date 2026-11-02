"""Market regime detection — deterministic composition of trend + volatility states."""

from __future__ import annotations

from indicators import adx, ema, historical_volatility, volatility_percentile


def trend_state(closes: list[float]) -> dict:
    e20 = ema(closes, 20)
    e50 = ema(closes, 50)
    e200 = ema(closes, 200) if len(closes) >= 200 else [None] * len(closes)
    last = closes[-1]
    v20, v50, v200 = e20[-1], e50[-1], e200[-1]
    score = 0
    checks = []
    if v20 is not None:
        checks.append(("price>ema20", last > v20))
    if v50 is not None:
        checks.append(("price>ema50", last > v50))
    if v20 is not None and v50 is not None:
        checks.append(("ema20>ema50", v20 > v50))
    if v200 is not None:
        checks.append(("price>ema200", last > v200))
    score = sum(1 for _, ok in checks if ok)
    trend = "up" if score >= 3 else "down" if score <= 1 else "sideways"
    return {"trend": trend, "score": score, "checks": checks}


def vol_state(closes: list[float]) -> dict:
    hv = historical_volatility(closes, 20)
    vp = volatility_percentile(hv, lookback=252)
    vp_last = next((v for v in reversed(vp) if v is not None), None)
    hv_last = next((v for v in reversed(hv) if v is not None), None)
    if vp_last is None:
        return {"vol_regime": "unknown", "hv": None, "percentile": None}
    regime = "low" if vp_last < 25 else "high" if vp_last > 75 else "normal"
    return {"vol_regime": regime, "hv": round(hv_last, 2) if hv_last else None,
            "percentile": round(vp_last, 1)}


def strength_state(highs: list[float], lows: list[float], closes: list[float]) -> dict:
    a, pdi, mdi = adx(highs, lows, closes)
    adx_last = next((v for v in reversed(a) if v is not None), None)
    pdi_last = next((v for v in reversed(pdi) if v is not None), None)
    mdi_last = next((v for v in reversed(mdi) if v is not None), None)
    strength = "unknown" if adx_last is None else (
        "strong" if adx_last >= 25 else "moderate" if adx_last >= 20 else "weak"
    )
    return {"adx": round(adx_last, 1) if adx_last else None, "strength": strength,
            "di": {"plus": round(pdi_last, 1) if pdi_last else None,
                   "minus": round(mdi_last, 1) if mdi_last else None}}


def regime_report(closes: list[float], highs: list[float], lows: list[float]) -> dict:
    t = trend_state(closes)
    v = vol_state(closes)
    s = strength_state(highs, lows, closes)
    label = f"{t['trend']} trend / {v['vol_regime']} vol / {s['strength']}"
    return {
        "regime": label,
        "trend": t,
        "vol": v,
        "strength": s,
        "note": "deterministic composition of EMA alignment, volatility percentile and ADX",
    }
