"""AI analyst API: generate, latest, history + news classification."""

from __future__ import annotations

import json
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ai import graph as analyst_graph
from app.db import get_pool
from app.marketdata import store
from providers.llm import LLMConfig, chat

router = APIRouter(prefix="/v1/analysis", tags=["ai-analyst"])


class GenerateRequest(BaseModel):
    symbol: str = "XAUUSD"
    interval: str = "1day"


@router.post("/generate")
async def generate(req: GenerateRequest) -> dict:
    symbol = req.symbol.upper()
    with get_pool().connection() as conn:
        inst = store.get_instrument_by_symbol(conn, symbol)
    if inst is None:
        raise HTTPException(status_code=404, detail=f"unknown instrument {symbol}")
    if not inst["enabled"]:
        raise HTTPException(status_code=409, detail=f"instrument {symbol} is not enabled")
    try:
        return await analyst_graph.run_analysis(symbol, req.interval)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"analysis failed: {exc}") from exc


def _row_to_analysis(r) -> dict:
    return {
        "id": r["id"],
        "symbol": r["symbol"],
        "interval": r["interval"],
        "status": r["status"],
        "model": r["model"],
        "prompt_version": r["prompt_version"],
        "evidence_hash": r["evidence_hash"],
        "summary": r["summary"],
        "scenarios": r["scenarios"],
        "risk": r["risk"],
        "data_warnings": r["data_warnings"],
        "cache_hit": r["cache_hit"],
        "generated_at": r["generated_at"].isoformat() if r["generated_at"] else None,
    }


@router.get("/latest/{symbol}")
def latest(symbol: str, interval: str | None = None) -> dict:
    symbol = symbol.upper()
    with get_pool().connection() as conn:
        cur = conn.execute(
            """
            SELECT * FROM market_analyses
            WHERE symbol = %s AND (%s::text IS NULL OR interval = %s)
            ORDER BY generated_at DESC LIMIT 1
            """,
            (symbol, interval, interval),
        )
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="no analysis yet — run POST /v1/analysis/generate")
    return _row_to_analysis(row)


@router.get("/history/{symbol}")
def history(symbol: str, limit: int = 10) -> dict:
    symbol = symbol.upper()
    with get_pool().connection() as conn:
        cur = conn.execute(
            """
            SELECT id, symbol, interval, status, model, prompt_version, evidence_hash,
                   summary, cache_hit, generated_at
            FROM market_analyses
            WHERE symbol = %s
            ORDER BY generated_at DESC LIMIT %s
            """,
            (symbol, min(limit, 50)),
        )
        rows = cur.fetchall()
    return {
        "count": len(rows),
        "analyses": [
            {
                "id": r["id"], "interval": r["interval"], "status": r["status"],
                "model": r["model"], "evidence_hash": r["evidence_hash"][:12],
                "summary": (r["summary"] or "")[:160],
                "cache_hit": r["cache_hit"],
                "generated_at": r["generated_at"].isoformat() if r["generated_at"] else None,
            }
            for r in rows
        ],
    }


@router.post("/classify-news")
async def classify_news(limit: int = 30) -> dict:
    """Classify unclassified news with ONE batched, cached LLM call."""
    from app.db import get_pool
    from app.macrodata import latest_news

    articles = [a for a in latest_news(limit * 2) if not a["classified"]][:limit]
    if not articles:
        return {"classified": 0, "note": "no unclassified articles"}
    cfg = LLMConfig()
    if not cfg.configured:
        raise HTTPException(status_code=503, detail="LLM_API_KEY not set — classification unavailable (honest skip)")

    payload = [
        {"i": i, "title": a["title"], "summary": (a["summary"] or "")[:300]}
        for i, a in enumerate(articles)
    ]
    messages = [
        {
            "role": "system",
            "content": (
                "You classify gold-market news headlines. For each item output a sentiment "
                "'bullish'|'bearish'|'neutral' for GOLD (XAU/USD) and affected instruments. "
                "Be conservative: only label sentiment when the headline clearly implies it. "
                "Output STRICT JSON: [{\"i\": <int>, \"sentiment\": \"...\", \"instruments\": [\"XAUUSD\"], \"reason\": \"<short>\"}]. "
                "No prose outside JSON. Never invent facts beyond the headline text."
            ),
        },
        {"role": "user", "content": __import__("json").dumps(payload)},
    ]
    try:
        result = await chat(messages, cfg=cfg, max_tokens=1500)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM classification failed: {exc}") from exc

    text = result["content"].strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*$", "", text)
    try:
        items = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"classifier returned invalid JSON: {exc}") from exc

    updated = 0
    url_by_index = {i: a["url"] for i, a in enumerate(articles)}
    with get_pool().connection() as conn:
        for item in items:
            idx = item.get("i")
            sentiment = item.get("sentiment")
            if idx not in url_by_index or sentiment not in ("bullish", "bearish", "neutral"):
                continue
            conn.execute(
                """
                UPDATE news_articles
                SET classified = true, sentiment = %s, instruments = %s
                WHERE url = %s
                """,
                (sentiment, json.dumps(item.get("instruments", [])), url_by_index[idx]),
            )
            updated += 1
    return {"classified": updated, "cache_hit": result.get("cache_hit", False), "model": result.get("model")}
