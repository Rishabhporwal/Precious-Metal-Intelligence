"""Technical analysis API: indicators + market structure (computed on demand
from stored candles — deterministic and versioned by ALGO_VERSION)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.db import get_pool
from app.marketdata import store
from indicators import (
    adx,
    atr,
    bollinger,
    divergence,
    ema,
    historical_volatility,
    macd,
    realized_volatility,
    roc,
    rsi,
    sma,
    stochastic,
    volatility_percentile,
)
from indicators import structure as st
from providers.base import CandleInterval

router = APIRouter(prefix="/v1/instruments", tags=["technical-analysis"])

ALGO_VERSION = "indicators-1.0.0"


def _floats(rows: list[dict], key: str) -> list[float]:
    return [float(r[key]) for r in rows]


def _series_payload(series: list[float | None], rows: list[dict], tail: int = 5) -> list[dict]:
    """Tail of a series as time-anchored points (for charting overlays)."""
    out = []
    for i, v in enumerate(series):
        if v is None:
            continue
        ts = rows[i]["market_ts"]
        out.append({
            "time": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
            "value": round(v, 6),
        })
    return out[-tail:]


def _load_candles(symbol: str, interval: CandleInterval, limit: int) -> list[dict]:
    with get_pool().connection() as conn:
        instrument = store.get_instrument_by_symbol(conn, symbol)
        if instrument is None:
            raise HTTPException(status_code=404, detail=f"unknown instrument {symbol}")
        if not instrument["enabled"]:
            raise HTTPException(status_code=409, detail=f"instrument {symbol} is not enabled")
        return store.get_candles(conn, instrument["id"], interval, limit=limit)


@router.get("/{symbol}/indicators")
def indicators(
    symbol: str,
    interval: CandleInterval = Query(default=CandleInterval.DAY_1),
    limit: int = Query(default=1000, ge=60, le=5000),
) -> dict:
    symbol = symbol.upper()
    rows = _load_candles(symbol, interval, limit)
    if len(rows) < 60:
        raise HTTPException(status_code=409, detail="not enough stored candles for indicators")
    closes = _floats(rows, "close")
    highs = _floats(rows, "high")
    lows = _floats(rows, "low")

    e9, e20, e50 = ema(closes, 9), ema(closes, 20), ema(closes, 50)
    e100, e200 = ema(closes, 100), ema(closes, 200)
    s50, s200 = sma(closes, 50), sma(closes, 200)
    r = rsi(closes)
    macd_line, signal_line, hist = macd(closes)
    stoch_k, stoch_d = stochastic(highs, lows, closes)
    adx_v, pdi, mdi = adx(highs, lows, closes)
    atr_v = atr(highs, lows, closes)
    bb_u, bb_m, bb_l = bollinger(closes)
    hv = historical_volatility(closes)
    rv = realized_volatility(closes)
    vp = volatility_percentile(hv)
    roc_v = roc(closes)
    rsi_div = divergence(closes, r)
    macd_div = divergence(closes, hist)

    def last(s: list[float | None]) -> float | None:
        for v in reversed(s):
            if v is not None:
                return round(v, 6)
        return None

    return {
        "symbol": symbol,
        "interval": interval.value,
        "algo_version": ALGO_VERSION,
        "candles_used": len(rows),
        "latest": {
            "ema9": last(e9), "ema20": last(e20), "ema50": last(e50),
            "ema100": last(e100), "ema200": last(e200),
            "sma50": last(s50), "sma200": last(s200),
            "rsi14": last(r),
            "macd": {"line": last(macd_line), "signal": last(signal_line), "hist": last(hist)},
            "stoch": {"k": last(stoch_k), "d": last(stoch_d)},
            "adx14": last(adx_v), "plus_di": last(pdi), "minus_di": last(mdi),
            "atr14": last(atr_v),
            "bollinger": {"upper": last(bb_u), "mid": last(bb_m), "lower": last(bb_l)},
            "historical_volatility": last(hv),
            "realized_volatility": last(rv),
            "volatility_percentile": last(vp),
            "roc9": last(roc_v),
        },
        "divergences": {
            "rsi": [{"kind": d.kind, "detail": d.detail} for d in rsi_div[-3:]],
            "macd_hist": [{"kind": d.kind, "detail": d.detail} for d in macd_div[-3:]],
        },
        # tails for UI charting (EMA overlay etc.)
        "series_tail": {
            "ema20": _series_payload(e20, rows, 500),
            "ema50": _series_payload(e50, rows, 500),
            "ema200": _series_payload(e200, rows, 500),
        },
    }


@router.get("/{symbol}/structure")
def structure(
    symbol: str,
    interval: CandleInterval = Query(default=CandleInterval.HOUR_1),
    limit: int = Query(default=1000, ge=60, le=5000),
) -> dict:
    symbol = symbol.upper()
    rows = _load_candles(symbol, interval, limit)
    highs, lows, closes = _floats(rows, "high"), _floats(rows, "low"), _floats(rows, "close")

    daily = _load_candles(symbol, CandleInterval.DAY_1, 400)
    hourly = _load_candles(symbol, CandleInterval.HOUR_1, 72)

    report = st.full_structure_report(highs, lows, closes, daily, hourly)

    # multi-timeframe trend across stored intervals
    closes_by, highs_by, lows_by = {}, {}, {}
    for iv in (CandleInterval.HOUR_1, CandleInterval.HOUR_4, CandleInterval.DAY_1):
        try:
            mrows = _load_candles(symbol, iv, 1000)
        except HTTPException:
            mrows = []
        if len(mrows) >= 60:
            closes_by[iv.value] = _floats(mrows, "close")
            highs_by[iv.value] = _floats(mrows, "high")
            lows_by[iv.value] = _floats(mrows, "low")
    mtf = st.mtf_trend(closes_by, highs_by, lows_by)

    return {
        "symbol": symbol,
        "interval": interval.value,
        "algo_version": ALGO_VERSION,
        "candles_used": len(rows),
        "trend": report.trend,
        "swings": [
            {"index": s.index, "confirmed_at": s.confirmed_index, "kind": s.kind,
             "price": round(s.price, 6)}
            for s in report.swings
        ],
        "labels": [{"index": i, "label": l} for i, l in report.labels],
        "events": [
            {"kind": e.kind, "index": e.index, "level": round(e.level, 6), "detail": e.detail}
            for e in report.events
        ],
        "supports": [{"price": round(l["price"], 6), "touches": l["touches"]} for l in report.supports],
        "resistances": [{"price": round(l["price"], 6), "touches": l["touches"]} for l in report.resistances],
        "prev_day": {"high": report.pdh, "low": report.pdl},
        "prev_week": {"high": report.pwh, "low": report.pwl},
        "sessions": report.sessions,
        "mtf_trend": mtf,
    }
