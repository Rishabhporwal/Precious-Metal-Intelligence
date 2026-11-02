"""Quant statistics API: correlations, regime, historical scenario stats."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query

from app.db import get_pool
from app.marketdata import store
from providers.base import CandleInterval
from quant import correlations as corr
from quant import regimes as reg
from quant import scenarios as scn

router = APIRouter(prefix="/v1/instruments", tags=["quant-stats"])

ALGO_VERSION = "quant-1.0.0"

# macro series used for correlation vs gold daily returns
CORR_SERIES = ("DGS10", "DFII10", "DTWEXBGS", "DCOILWTICO")


@router.get("/{symbol}/quant")
def quant_stats(
    symbol: str,
    window: int = Query(default=30, ge=10, le=120),
) -> dict:
    symbol = symbol.upper()
    with get_pool().connection() as conn:
        instrument = store.get_instrument_by_symbol(conn, symbol)
        if instrument is None:
            raise HTTPException(status_code=404, detail=f"unknown instrument {symbol}")
        if not instrument["enabled"]:
            raise HTTPException(status_code=409, detail=f"instrument {symbol} is not enabled")
        daily = store.get_candles(conn, instrument["id"], CandleInterval.DAY_1, limit=5000)
        macro_rows = []
        for sid in CORR_SERIES:
            cur = conn.execute(
                """
                SELECT series_id, as_of_date, value, fetched_at
                FROM macro_observations
                WHERE provider = 'fred' AND series_id = %s
                ORDER BY as_of_date, fetched_at
                """,
                (sid,),
            )
            macro_rows.extend(cur.fetchall())
        # counterpart instrument (silver) for gold/silver correlation
        counterpart = store.get_instrument_by_symbol(conn, "XAGUSD")
        silver_daily = []
        if counterpart is not None:
            silver_daily = store.get_candles(conn, counterpart["id"], CandleInterval.DAY_1, limit=400)

    if len(daily) < 260:
        raise HTTPException(status_code=409, detail="need >= 260 daily candles for quant statistics")

    closes = [float(r["close"]) for r in daily]
    highs = [float(r["high"]) for r in daily]
    lows = [float(r["low"]) for r in daily]
    times = [r["market_ts"] for r in daily]

    regime = reg.regime_report(closes, highs, lows)
    scenario = scn.scenario_report(closes)

    macro_series = {}
    for sid in CORR_SERIES:
        rows = [r for r in macro_rows if r["series_id"] == sid]
        if rows:
            macro_series[sid] = corr.build_series(rows)
    correlations = corr.correlation_summary(times, closes, macro_series, window=window)

    # gold/silver correlation on overlapping daily closes
    silver_corr = None
    if len(silver_daily) >= 60:
        s_dates = {corr._to_date(r["market_ts"]): float(r["close"]) for r in silver_daily}
        overlap_dates, gold_v, silver_v = [], [], []
        for t, c in zip(times, closes, strict=False):
            d = corr._to_date(t)
            if d in s_dates:
                overlap_dates.append(d)
                gold_v.append(c)
                silver_v.append(s_dates[d])
        if len(overlap_dates) >= 60:
            gold_r = corr.returns(gold_v)
            silver_r = corr.returns(silver_v)
            paired = [(g, s) for g, s in zip(gold_r, silver_r, strict=True) if g is not None and s is not None]
            full = corr.pearson([p[0] for p in paired], [p[1] for p in paired]) if paired else None
            recent_window = 30
            recent_pairs = list(zip(gold_r[-recent_window:], silver_r[-recent_window:], strict=True))
            recent_pairs = [(g, s) for g, s in recent_pairs if g is not None and s is not None]
            recent = corr.pearson([p[0] for p in recent_pairs], [p[1] for p in recent_pairs]) if recent_pairs else None
            caveat = None
            if full is not None and abs(full) < 0.2:
                caveat = (
                    "near-zero gold/silver correlation is atypical — free-plan SI daily data "
                    "shows large session gaps; treat this series with caution"
                )
            silver_corr = {
                "counterpart": "XAGUSD",
                "note": "stored silver data is COMEX SI futures (parked proxy)",
                "overlap_days": len(overlap_dates),
                "full_sample": round(full, 3) if full is not None else None,
                f"last_{recent_window}d": round(recent, 3) if recent is not None else None,
                "data_quality_caveat": caveat,
            }

    return {
        "symbol": symbol,
        "algo_version": ALGO_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "candles_used": len(daily),
        "regime": regime,
        "correlations": correlations,
        "gold_silver": silver_corr,
        "scenarios": scenario,
    }
