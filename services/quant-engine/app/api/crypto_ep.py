"""Crypto order-flow endpoints — BTC/ETH/SOL from the OpenMarket ingestion."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.db import get_pool

router = APIRouter(prefix="/v1/crypto", tags=["crypto-orderflow"])


@router.get("/candles")
def candles(symbol: str = Query(default="BTC"), limit: int = Query(default=120, ge=1, le=500)) -> dict:
    symbol = symbol.upper()
    with get_pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT market_ts, open, high, low, close, buy_volume, sell_volume
            FROM crypto_candles WHERE symbol = %s ORDER BY market_ts DESC LIMIT %s
            """,
            (symbol, limit),
        ).fetchall()
    rows.reverse()
    return {
        "symbol": symbol,
        "count": len(rows),
        "candles": [
            {
                "market_ts": r["market_ts"].isoformat() if r["market_ts"] else None,
                "open": str(r["open"]), "high": str(r["high"]),
                "low": str(r["low"]), "close": str(r["close"]),
                "buy_volume": str(r["buy_volume"]) if r["buy_volume"] is not None else None,
                "sell_volume": str(r["sell_volume"]) if r["sell_volume"] is not None else None,
            }
            for r in rows
        ],
    }


@router.get("/overview")
def overview() -> dict:
    """Latest state per symbol: price, buy/sell pressure, OI, funding, liquidations."""
    out = []
    with get_pool().connection() as conn:
        for symbol in ("BTC", "ETH", "SOL"):
            candle = conn.execute(
                """
                SELECT market_ts, close, buy_volume, sell_volume FROM crypto_candles
                WHERE symbol = %s ORDER BY market_ts DESC LIMIT 24
                """,
                (symbol,),
            ).fetchall()
            deriv = conn.execute(
                """
                SELECT market_ts, open_interest, funding_rate, liq_buy, liq_sell FROM crypto_deriv
                WHERE symbol = %s ORDER BY market_ts DESC LIMIT 1
                """,
                (symbol,),
            ).fetchone()
            if not candle:
                out.append({"symbol": symbol, "has_data": False})
                continue
            buys = sum(float(c["buy_volume"] or 0) for c in candle)
            sells = sum(float(c["sell_volume"] or 0) for c in candle)
            flow_total = buys + sells
            prev_close = candle[0]["close"]  # newest is index 0
            out.append(
                {
                    "symbol": symbol,
                    "has_data": True,
                    "price": str(candle[0]["close"]),
                    "as_of": candle[0]["market_ts"].isoformat() if candle[0]["market_ts"] else None,
                    "buy_share_24h": round(buys / flow_total, 4) if flow_total else None,
                    "buy_volume_24h": buys,
                    "sell_volume_24h": sells,
                    "change_pct": (
                        round((float(candle[-1]["close"]) - float(prev_close)) / float(prev_close) * 100, 2)
                        if len(candle) > 1 and float(prev_close)
                        else None
                    ),
                    "open_interest": str(deriv["open_interest"]) if deriv and deriv["open_interest"] is not None else None,
                    "funding_rate": str(deriv["funding_rate"]) if deriv and deriv["funding_rate"] is not None else None,
                    "liq_1h": {
                        "buy": str(deriv["liq_buy"]) if deriv and deriv["liq_buy"] is not None else None,
                        "sell": str(deriv["liq_sell"]) if deriv and deriv["liq_sell"] is not None else None,
                    }
                    if deriv
                    else None,
                }
            )
    return {"symbols": out, "configured": True}
