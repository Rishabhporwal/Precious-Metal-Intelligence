"""Market data API (internal v1). All data access logic lives here — the
Fastify gateway only proxies and validates."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.db import get_pool
from app.marketdata import store
from app.marketdata.provider_factory import load_provider
from providers.base import CandleInterval, ProviderError, ProviderUnconfigured
from providers.twelve_data import TwelveDataProvider

router = APIRouter(prefix="/v1", tags=["market-data"])


def _provider() -> TwelveDataProvider:
    return load_provider()


@router.get("/instruments")
def instruments() -> dict:
    with get_pool().connection() as conn:
        rows = store.list_instruments(conn)
        counts = store.candle_counts(conn)
    out = []
    for r in rows:
        c = counts.get(r["symbol"], {})
        last_daily = c.get("last_daily")
        last_hourly = c.get("last_hourly")
        out.append(
            {
                **r,
                "freshness": {
                    "last_daily": last_daily.isoformat() if last_daily else None,
                    "last_hourly": last_hourly.isoformat() if last_hourly else None,
                    "daily_count": c.get("daily_count", 0),
                    "hourly_count": c.get("hourly_count", 0),
                },
            }
        )
    return {"instruments": out}


@router.post("/instruments/{symbol}/verify")
def verify_instrument(symbol: str) -> dict:
    """Live Twelve Data entitlement verification. Updates registry on success."""
    with get_pool().connection() as conn:
        instrument = store.get_instrument_by_symbol(conn, symbol)
    if instrument is None:
        raise HTTPException(status_code=404, detail=f"unknown instrument {symbol}")

    candidate = instrument.get("provider_symbol") or symbol.replace("USD", "/USD")
    try:
        provider = _provider()
        result = provider.verify_instrument(candidate)
    except ProviderUnconfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=f"provider error: {exc}") from exc

    with get_pool().connection() as conn:
        store.set_entitlement(
            conn,
            instrument["id"],
            result.provider_symbol,
            verified=result.available,
            enabled=result.available,
            note=result.note,
        )
    return {
        "symbol": symbol,
        "provider_symbol": result.provider_symbol,
        "available": result.available,
        "quote_ok": result.quote_ok,
        "history_ok": result.history_ok,
        "history_from": result.history_from.isoformat() if result.history_from else None,
        "history_to": result.history_to.isoformat() if result.history_to else None,
        "note": result.note,
        "details": result.details,
    }


class BackfillRequest(BaseModel):
    interval: CandleInterval = CandleInterval.DAY_1
    start: datetime | None = None
    end: datetime | None = None
    limit: int = Field(default=5000, ge=1, le=5000)


@router.post("/instruments/{symbol}/backfill")
def backfill(symbol: str, req: BackfillRequest) -> dict:
    with get_pool().connection() as conn:
        instrument = store.get_instrument_by_symbol(conn, symbol)
        if instrument is None:
            raise HTTPException(status_code=404, detail=f"unknown instrument {symbol}")
        if not (instrument["enabled"] and instrument["entitlement_verified"]):
            raise HTTPException(
                status_code=409,
                detail="instrument not verified/enabled — run /verify first",
            )
        provider_row = conn.execute(
            "SELECT id FROM data_providers WHERE name = 'twelvedata'"
        ).fetchone()
        provider_id = int(provider_row["id"])

    provider = _provider()
    try:
        candles = provider.fetch_candles(
            instrument["provider_symbol"], req.interval, start=req.start, end=req.end, limit=req.limit
        )
    except ProviderUnconfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=f"provider error: {exc}") from exc

    raw = {
        "symbol": instrument["provider_symbol"],
        "interval": req.interval.value,
        "count": len(candles),
    }
    with get_pool().connection() as conn:
        store.record_observation(conn, provider_id, instrument["provider_symbol"], "time_series", raw, ok=True)
        written = store.upsert_candles(conn, instrument["id"], provider_id, req.interval, candles)
    return {
        "symbol": symbol,
        "interval": req.interval.value,
        "fetched": len(candles),
        "written": written,
        "first": candles[0].market_ts.isoformat() if candles else None,
        "last": candles[-1].market_ts.isoformat() if candles else None,
    }


@router.get("/instruments/{symbol}/candles")
def candles(
    symbol: str,
    interval: CandleInterval = Query(default=CandleInterval.DAY_1),
    limit: int = Query(default=500, ge=1, le=5000),
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict:
    with get_pool().connection() as conn:
        instrument = store.get_instrument_by_symbol(conn, symbol)
        if instrument is None:
            raise HTTPException(status_code=404, detail=f"unknown instrument {symbol}")
        rows = store.get_candles(conn, instrument["id"], interval, limit=limit, start=start, end=end)
    return {
        "symbol": symbol,
        "interval": interval.value,
        "count": len(rows),
        "candles": [
            {
                "market_ts": r["market_ts"].isoformat() if r["market_ts"] else None,
                "open": str(r["open"]),
                "high": str(r["high"]),
                "low": str(r["low"]),
                "close": str(r["close"]),
                "volume": str(r["volume"]) if r["volume"] is not None else None,
                "volume_type": r["volume_type"],
                "status": r["candle_status"],
            }
            for r in rows
        ],
    }


@router.get("/instruments/{symbol}/quote")
def quote(symbol: str) -> dict:
    with get_pool().connection() as conn:
        instrument = store.get_instrument_by_symbol(conn, symbol)
        if instrument is None:
            raise HTTPException(status_code=404, detail=f"unknown instrument {symbol}")
        latest = store.get_latest_quote(conn, instrument["id"])
    if latest is None:
        raise HTTPException(status_code=404, detail=f"no quote stored yet for {symbol}")
    return {
        "symbol": symbol,
        "price": str(latest["price"]),
        "bid": str(latest["bid"]) if latest["bid"] is not None else None,
        "ask": str(latest["ask"]) if latest["ask"] is not None else None,
        "market_ts": latest["market_ts"].isoformat() if latest["market_ts"] else None,
        "received_at": latest["received_at"].isoformat() if latest["received_at"] else None,
    }


@router.get("/data/status")
def data_status() -> dict:
    with get_pool().connection() as conn:
        counts = store.candle_counts(conn)
        now = datetime.now(UTC)
    return {"server_time_utc": now.isoformat(), "instruments": counts}
