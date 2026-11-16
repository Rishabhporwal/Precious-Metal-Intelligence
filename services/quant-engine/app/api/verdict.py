"""Daily Verdict API — generate + latest.

The verdict is the product's single deliverable: one call on gold with a
concrete plan. Numbers are computed deterministically in ai/verdict.py; the
LLM (if configured) writes only the narrative, receiving the computed plan.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ai.verdict import build_verdict
from app.db import get_pool
from app.macrodata import latest_news, upcoming_events
from app.marketdata import store
from providers.base import CandleInterval
from strategies.engine import recent_detections

router = APIRouter(prefix="/v1/verdict", tags=["verdict"])

HIGH_IMPACT_HINT = "CPI, NFP, FOMC, PCE within 48h forces stand-aside"


# Driver weights: rates/USD move gold hard and last; geopolitics hits fast but
# fades; physical/positioning are slower burn. Deterministic, documented.
DRIVER_WEIGHTS = {
    "rates": 1.0, "usd": 1.0, "geopolitics": 0.8, "physical": 0.6,
    "positioning": 0.5, "market": 0.4, "other": 0.5,
}


def _news_net(articles: list[dict]) -> float | None:
    """Driver-weighted net news vote, clipped to ±0.5 (the news weight budget)."""
    votes: list[float] = []
    for a in articles:
        sent = a.get("sentiment")
        if not sent:
            continue
        driver = a.get("driver") or "other"
        w = DRIVER_WEIGHTS.get(driver, 0.5)
        votes.append(w if sent == "bullish" else -w if sent == "bearish" else 0.0)
    if not votes:
        return None
    raw = sum(votes)
    return round(max(-0.5, min(0.5, raw * 0.25)), 2)


def _strategy_bias_48h(symbol: str) -> dict:
    cutoff = datetime.now(UTC) - timedelta(hours=48)
    bull = bear = 0
    for d in recent_detections(symbol, None, 80):
        anchor = d.get("anchor_time")
        if not anchor:
            continue
        if anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=UTC)
        if anchor < cutoff:
            continue
        if d["direction"] == "bullish":
            bull += 1
        elif d["direction"] == "bearish":
            bear += 1
    return {"bullish": bull, "bearish": bear, "net": bull - bear}


async def _narrative(verdict: dict) -> tuple[str | None, dict | None]:
    """LLM writes the 'why' — it receives the computed plan and must not invent levels."""
    try:
        from providers.llm import LLMConfig, chat
    except Exception:  # noqa: BLE001
        return None, None
    cfg = LLMConfig(dict(os.environ))
    if not cfg.configured:
        return None, None

    plan = verdict.get("plan") or {}
    plan_txt = json.dumps(plan, indent=1) if plan else "stand-aside (no directional plan)"
    drivers_txt = "\n".join(f"- {d['plain']}" for d in verdict["drivers"]) or "- no strong signals either way"
    events_txt = ", ".join(e["release"] for e in verdict["event_risk"]["events"]) or "none within 48h"

    sys_prompt = (
        "You are a gold market analyst writing a short brief for a retail investor."
        " You are GIVEN the conclusion and the exact trade plan numbers — they were computed"
        " deterministically. Do NOT invent, change, or add any numbers, levels, or prices."
        " Write 3-5 sentences: what gold is doing, why (use the drivers), what the plan is"
        " (you may restate the given numbers verbatim), and the main risk."
        " Plain language, no jargon without a one-line explanation. No disclaimers."
    )
    user_prompt = (
        f"Verdict: {verdict['direction'].upper()} (confidence: {verdict['confidence']})\n"
        f"Current price: {verdict['price']}\n"
        f"Drivers:\n{drivers_txt}\n"
        f"Upcoming high-impact events: {events_txt}\n"
        f"Computed plan: {plan_txt}\n"
        f"Invalidations: {'; '.join(verdict['invalidations'])}"
    )
    try:
        res = await chat(
            [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            cfg,
            max_tokens=400,
        )
        return res.get("content"), {"model": res.get("model"), "cache_hit": res.get("cache_hit")}
    except Exception:  # noqa: BLE001 — deterministic verdict ships without narrative
        return None, None


class VerdictOut(BaseModel):
    symbol: str = "XAUUSD"


def _persist(v: dict, narrative: str | None, llm_meta: dict | None) -> int:
    with get_pool().connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO daily_verdicts
                (symbol, as_of, price, direction, confidence, score, drivers,
                 event_risk, plan, invalidations, key_levels, narrative, llm_meta)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                v["symbol"], v["as_of"], v["price"], v["direction"], v["confidence"],
                v["score"], json.dumps(v["drivers"]), json.dumps(v["event_risk"]),
                json.dumps(v["plan"]), json.dumps(v["invalidations"]),
                json.dumps(v["key_levels"]), narrative,
                json.dumps(llm_meta) if llm_meta else None,
            ),
        )
        return int(cur.fetchone()["id"])


@router.post("/generate")
async def generate(symbol: str = Query(default="XAUUSD")) -> dict:
    symbol = symbol.upper()
    with get_pool().connection() as conn:
        inst = store.get_instrument_by_symbol(conn, symbol)
        if inst is None or not inst["enabled"]:
            raise HTTPException(status_code=409, detail=f"instrument {symbol} not available")
        quote = store.get_latest_quote(conn, inst["id"])
        daily = store.get_candles(conn, inst["id"], CandleInterval.DAY_1, limit=300)
        hourly = store.get_candles(conn, inst["id"], CandleInterval.HOUR_1, limit=72)

    price = float(quote["price"]) if quote and quote.get("price") is not None else None
    v = build_verdict(
        symbol=symbol,
        quote_price=price,
        daily=daily,
        hourly=hourly,
        strategy_bias=_strategy_bias_48h(symbol),
        events=upcoming_events(10, 1),
        news_net=_news_net(latest_news(30, classified_only=True)),
    )
    if "error" in v:
        raise HTTPException(status_code=409, detail=v["error"])

    narrative, llm_meta = await _narrative(v)
    vid = _persist(v, narrative, {**(llm_meta or {}), "evidence_split": v.get("evidence_split")})
    return {"verdict_id": vid, **v, "narrative": narrative, "llm_meta": llm_meta}


@router.get("/latest")
def latest(symbol: str = Query(default="XAUUSD")) -> dict:
    symbol = symbol.upper()
    with get_pool().connection() as conn:
        cur = conn.execute(
            """
            SELECT * FROM daily_verdicts WHERE symbol = %s ORDER BY as_of DESC LIMIT 1
            """,
            (symbol,),
        )
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="no verdict yet — generate one")
    row = dict(row)
    row["as_of"] = row["as_of"].isoformat() if row["as_of"] else None
    meta = row.get("llm_meta") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except ValueError:
            meta = {}  # corrupted meta — degrade to empty, never crash the read
    if isinstance(meta, dict) and "evidence_split" in meta:
        row["evidence_split"] = meta["evidence_split"]
    return row
