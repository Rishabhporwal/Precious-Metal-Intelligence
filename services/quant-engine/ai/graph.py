"""LangGraph AI analyst.

Topology (cost-frugal per user mandate):
    snapshot → [gather_technical, gather_strategies, gather_macro, gather_quant] (fan-out)
             → risk (deterministic) → synthesize (SINGLE cached LLM call) → validate
             → (retry once on violation) → fallback (deterministic) → persist

Guarantees:
- Risk numbers are computed in Python, never by the LLM.
- LLM output passes number-containment validation (every number must exist in
  the evidence pack) and Pydantic schema validation.
- Same evidence hash = no new LLM spend (Redis cache + DB dedupe).
- No key → deterministic fallback, flagged `deterministic_fallback` (honest).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from ai.prompts import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
from ai.validate import validate_llm_output
from app.db import get_pool
from app.macrodata import (
    cftc_positioning,
    latest_news,
    macro_series_summary,
    upcoming_events,
)
from providers.llm import LLMConfig, chat
from strategies import engine as strategy_engine

logger = logging.getLogger("analyst")


# --------------------------------------------------------------------------- #
# state


def _merge(left: dict | None, right: dict | None) -> dict:
    return {**(left or {}), **(right or {})}


class AnalystState(TypedDict):
    symbol: str
    interval: str
    warnings: list[str]
    evidence: Annotated[dict | None, _merge]
    risk: dict | None
    llm_content: str | None
    llm_meta: dict | None
    validation_errors: list[str]
    retry_count: int
    analysis: dict | None
    status: str


# --------------------------------------------------------------------------- #
# deterministic nodes


async def _to_thread(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


def _warn_stale_quote(symbol: str) -> list[str]:
    from app.marketdata import store

    warnings = []
    with get_pool().connection() as conn:
        inst = store.get_instrument_by_symbol(conn, symbol)
        if inst is None:
            return [f"unknown instrument {symbol}"]
        q = store.get_latest_quote(conn, inst["id"])
    if q is None:
        warnings.append("no quote stored yet for gold")
    else:
        age_min = (datetime.now(UTC) - q["received_at"]).total_seconds() / 60
        if age_min > 20:
            warnings.append(f"last quote is {age_min:.0f} minutes old — ingestion may be stalled")
    return warnings


async def snapshot(state: AnalystState) -> dict:
    warnings = await _to_thread(_warn_stale_quote, state["symbol"])
    return {"warnings": warnings}


async def gather_technical(state: AnalystState) -> dict:
    from app.api import technical

    ind = await _to_thread(technical.indicators, state["symbol"], __import__("providers.base", fromlist=["CandleInterval"]).CandleInterval.DAY_1, 1000)
    struct = await _to_thread(technical.structure, state["symbol"], __import__("providers.base", fromlist=["CandleInterval"]).CandleInterval.HOUR_1, 1000)
    ev = {
        "technical": {
            "daily_indicators": ind["latest"],
            "divergences": ind["divergences"],
            "structure_1h": {
                "trend": struct["trend"],
                "prev_day": struct["prev_day"],
                "prev_week": struct["prev_week"],
                "supports": struct["supports"],
                "resistances": struct["resistances"],
                "recent_events": struct["events"][-4:],
                "mtf_trend": struct["mtf_trend"],
            },
            "series_ref": ind["algo_version"],
        }
    }
    return {"evidence": ev}


async def gather_strategies(state: AnalystState) -> dict:
    dets = await _to_thread(strategy_engine.recent_detections, state["symbol"], "1h", 15)
    daily_dets = await _to_thread(strategy_engine.recent_detections, state["symbol"], "1day", 8)
    compact = lambda d: {
        "strategy_id": d["strategy_id"],
        "direction": d["direction"],
        "status": d["status"],
        "anchor_time": d["anchor_time"].isoformat() if d["anchor_time"] else None,
        "levels": {k: v for k, v in (d["levels"] or {}).items() if isinstance(v, (int, float))},
        "evidence": (d["evidence"] or [])[:2],
    }
    ev = {
        "strategies": {
            "detections_1h": [compact(d) for d in dets],
            "detections_1day": [compact(d) for d in daily_dets],
            "note": "detections are analysis records, not trade signals",
        }
    }
    return {"evidence": ev}


async def gather_macro(state: AnalystState) -> dict:
    series = await _to_thread(macro_series_summary)
    cftc = await _to_thread(cftc_positioning)
    events = await _to_thread(upcoming_events, 14, 7)
    news = await _to_thread(latest_news, 8)
    ev = {
        "macro": {
            "series": [
                {
                    "series_id": s["series_id"],
                    "value": str(s["value"]) if s["value"] is not None else None,
                    "as_of": str(s["as_of_date"]),
                    "change": str(s["change"]) if s["change"] is not None else None,
                }
                for s in series
            ],
            "cftc": [
                {
                    "series_id": c["series_id"],
                    "net_noncomm": str(c["value"]) if c["value"] is not None else None,
                    "report_date": str(c["as_of_date"]),
                    "pct_long": (c["meta"] or {}).get("pct_of_oi_noncomm_long"),
                    "pct_short": (c["meta"] or {}).get("pct_of_oi_noncomm_short"),
                }
                for c in cftc
            ],
            "calendar": [
                {"release": e["release_name"], "date": str(e["event_date"])}
                for e in events
            ],
            "news_headlines": [
                {"source": n["source"], "title": n["title"], "published": n["published_at"].isoformat() if n["published_at"] else None,
                 "sentiment": n["sentiment"]}
                for n in news
            ],
            "news_note": "headlines are unclassified unless sentiment is set; no impact claims without evidence",
        }
    }
    return {"evidence": ev}


async def gather_quant(state: AnalystState) -> dict:
    from app.api import quant_stats

    # explicit window: route defaults are FastAPI Query objects, not ints
    q = await _to_thread(quant_stats.quant_stats, state["symbol"], 30)
    ev = {
        "quant": {
            "regime": q["regime"]["regime"],
            "vol": q["regime"]["vol"],
            "strength": q["regime"]["strength"],
            "correlations": q["correlations"],
            "scenarios": {
                "current_bucket": q["scenarios"]["current_bucket"],
                "bucket_history": q["scenarios"]["bucket_history"],
                "baseline": q["scenarios"]["baseline"],
                "note": q["scenarios"]["note"],
            },
        }
    }
    return {"evidence": ev}


def _risk_calc(symbol: str) -> dict:
    from app.marketdata import store
    from indicators import atr as atr_fn
    from providers.base import CandleInterval

    with get_pool().connection() as conn:
        inst = store.get_instrument_by_symbol(conn, symbol)
        if inst is None:
            return {"error": f"unknown instrument {symbol}"}
        daily = store.get_candles(conn, inst["id"], CandleInterval.DAY_1, limit=30)
        q = store.get_latest_quote(conn, inst["id"])
        events = conn.execute(
            """
            SELECT release_name, event_date FROM economic_events
            WHERE event_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 2
            ORDER BY event_date
            """
        ).fetchall()

    closes = [float(r["close"]) for r in daily]
    highs = [float(r["high"]) for r in daily]
    lows = [float(r["low"]) for r in daily]
    atr_series = atr_fn(highs, lows, closes, 14)
    atr_last = next((v for v in reversed(atr_series) if v is not None), None)
    price = float(q["price"]) if q else None

    risk: dict[str, Any] = {
        "reference_price": price,
        "atr14_daily": round(atr_last, 3) if atr_last else None,
        "platform_reference_stop_distance": round(1.5 * atr_last, 3) if atr_last else None,
        "note": "stop distance is a deterministic ATR reference for risk sizing (Phase 8); not a trade recommendation",
        "high_impact_events_48h": [f"{e['release_name']} on {e['event_date']}" for e in events],
    }
    if events:
        risk["event_risk_warning"] = "high-impact releases within 48h — event risk policy applies (Phase 8)"
    return risk


async def risk_node(state: AnalystState) -> dict:
    risk = await _to_thread(_risk_calc, state["symbol"])
    return {"risk": risk}


# --------------------------------------------------------------------------- #
# synthesis


def _evidence_hash(evidence: dict, risk: dict) -> str:
    def strip_volatile(obj):
        if isinstance(obj, dict):
            return {k: strip_volatile(v) for k, v in obj.items() if k not in ("fetched_at", "generated_at", "received_at", "fetched")}
        if isinstance(obj, list):
            return [strip_volatile(v) for v in obj]
        return obj

    return hashlib.sha256(
        json.dumps({"e": strip_volatile(evidence), "r": strip_volatile(risk)}, sort_keys=True, default=str).encode()
    ).hexdigest()


def _deterministic_fallback(evidence: dict, risk: dict) -> dict:
    """Honest 3-scenario narrative built ONLY from evidence keys (no LLM)."""
    t = evidence.get("technical", {})
    q = evidence.get("quant", {})
    ind = t.get("daily_indicators", {})
    struct = t.get("structure_1h", {})
    rsi_v = ind.get("rsi14")
    trend = struct.get("trend", "unknown")
    regime = q.get("regime", "unknown")
    supports = [s["price"] for s in struct.get("supports", [])][:2]
    resistances = [r["price"] for r in struct.get("resistances", [])][:2]

    common = {
        "bullish": {
            "direction": "bullish",
            "narrative": (
                f"Scenario consistent with structure_1h.trend={trend} and quant.regime={regime}: "
                f"if price holds above technical.structure_1h.supports "
                f"({', '.join(str(round(s, 2)) for s in supports) or 'n/a'}), rotation toward "
                f"technical.structure_1h.resistances ({', '.join(str(round(r, 2)) for r in resistances) or 'n/a'}) "
                f"remains on the table. RSI(14)={rsi_v} does not contradict it."
            ),
            "supporting": ["technical.structure_1h.trend", "quant.regime", "technical.structure_1h.supports"],
            "conflicting": ["technical.daily_indicators.macd" ],
            "confirmation": "hold above listed supports with structure_1h trend intact",
            "invalidation": f"close below the listed support levels ({', '.join(str(round(s, 2)) for s in supports) or 'n/a'})",
        },
        "neutral": {
            "direction": "neutral",
            "narrative": (
                f"Range read: price oscillating between structure_1h.supports and resistances "
                f"while quant.regime={regime} and RSI(14)={rsi_v} sits mid-range. "
                f"No directional edge claimed without new evidence."
            ),
            "supporting": ["quant.regime", "technical.daily_indicators.rsi14"],
            "conflicting": [],
            "confirmation": "continued oscillation between the listed S/R levels",
            "invalidation": "decisive close beyond either listed S/R boundary",
        },
        "bearish": {
            "direction": "bearish",
            "narrative": (
                f"Scenario consistent with technical.daily_indicators EMA stack and "
                f"quant.regime={regime}: failure at structure_1h.resistances "
                f"({', '.join(str(round(r, 2)) for r in resistances) or 'n/a'}) would favor "
                f"a retest of supports ({', '.join(str(round(s, 2)) for s in supports) or 'n/a'})."
            ),
            "supporting": ["technical.daily_indicators", "quant.regime", "technical.structure_1h.resistances"],
            "conflicting": ["strategies.detections_1h (any bullish CHoCH/MSS records)"],
            "confirmation": "rejection at the listed resistances",
            "invalidation": f"close above the listed resistance levels ({', '.join(str(round(r, 2)) for r in resistances) or 'n/a'})",
        },
    }
    return {
        "summary": (
            f"Deterministic fallback summary (no LLM configured or validation failed): "
            f"structure_1h trend={trend}, quant regime={regime}, RSI(14)={rsi_v}. "
            f"Scenarios below restate platform evidence only."
        ),
        "scenarios": [common["bullish"], common["neutral"], common["bearish"]],
        "data_warnings": ["generated by deterministic fallback — no LLM narrative"],
    }


def _find_existing_analysis(symbol: str, interval: str, evidence_hash: str) -> dict | None:
    with get_pool().connection() as conn:
        cur = conn.execute(
            """
            SELECT scenarios, summary, status, model, generated_at
            FROM market_analyses
            WHERE symbol = %s AND interval = %s AND evidence_hash = %s
            ORDER BY generated_at DESC LIMIT 1
            """,
            (symbol, interval, evidence_hash),
        )
        return cur.fetchone()


async def synthesize(state: AnalystState) -> dict:
    evidence, risk = state["evidence"], state["risk"]
    eh = _evidence_hash(evidence, risk)

    # Cost gate: identical evidence already analyzed → reuse, zero LLM spend.
    existing = await _to_thread(_find_existing_analysis, state["symbol"], state["interval"], eh)
    if existing is not None:
        return {
            "llm_content": None,
            "llm_meta": {"cache_hit": True, "note": "identical evidence already analyzed — zero LLM spend"},
            "status": existing["status"],
            "analysis": {
                "summary": existing["summary"] or "",
                "scenarios": existing["scenarios"],
                "data_warnings": [f"reused existing analysis from {existing['generated_at']}"],
                "already_existed": True,
            },
        }

    cfg = LLMConfig()
    feedback = ""
    if state.get("validation_errors"):
        feedback = (
            "\n\nYOUR PREVIOUS OUTPUT WAS REJECTED FOR:\n- "
            + "\n- ".join(state["validation_errors"])
            + "\nFix these issues. Remember: only numbers present in the evidence."
        )
    user = build_user_prompt(evidence, risk) + feedback
    try:
        result = await chat(
            [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}],
            cfg=cfg,
        )
        return {
            "llm_content": result["content"],
            "llm_meta": {
                "model": result["model"],
                "cache_hit": result["cache_hit"],
                "usage": result.get("usage", {}),
                "prompt_version": cfg.prompt_version,
            },
        }
    except Exception as exc:  # noqa: BLE001 — fall back honestly
        logger.warning("LLM synthesis failed (%s) — deterministic fallback", exc)
        return {
            "llm_content": None,
            "llm_meta": {"error": str(exc), "prompt_version": cfg.prompt_version},
            "status": "deterministic_fallback",
        }


async def validate(state: AnalystState) -> dict:
    if state.get("llm_content") is None:
        analysis = _deterministic_fallback(state["evidence"] or {}, state["risk"] or {})
        return {"analysis": analysis, "status": "deterministic_fallback",
                "validation_errors": state.get("validation_errors", [])}

    out, errors = validate_llm_output(state["llm_content"], state["evidence"] or {}, state["risk"] or {})
    if out is None and state.get("retry_count", 0) < 1:
        return {"validation_errors": errors, "retry_count": state.get("retry_count", 0) + 1,
                "needs_retry": True}
    if out is None:
        analysis = _deterministic_fallback(state["evidence"] or {}, state["risk"] or {})
        return {
            "analysis": analysis,
            "status": "deterministic_fallback",
            "validation_errors": errors,
        }
    analysis = out.model_dump()
    warnings = state.get("warnings", []) + analysis.get("data_warnings", [])
    return {"analysis": analysis, "status": "llm", "warnings": warnings, "needs_retry": False}


async def persist(state: AnalystState) -> dict:
    analysis, evidence, risk = state["analysis"], state["evidence"], state["risk"]
    if analysis is None:
        # exhausted validation — final fallback so a run never ends empty
        fallback = _deterministic_fallback(evidence or {}, risk or {})
        return {"analysis": fallback, "status": "deterministic_fallback"}
    eh = _evidence_hash(evidence, risk)
    llm_meta = state.get("llm_meta") or {}

    def _write() -> int:
        with get_pool().connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO market_analyses
                    (symbol, interval, status, model, prompt_version, evidence_hash,
                     scenarios, risk, data_warnings, summary, cache_hit)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, interval, evidence_hash) DO NOTHING
                RETURNING id
                """,
                (
                    state["symbol"], state["interval"], state["status"],
                    llm_meta.get("model"), PROMPT_VERSION, eh,
                    json.dumps(analysis["scenarios"], default=str),
                    json.dumps(risk, default=str),
                    json.dumps(state.get("warnings", []), default=str),
                    analysis["summary"],
                    llm_meta.get("cache_hit", False),
                ),
            )
            row = cur.fetchone()
            if row is None:
                return 0  # identical evidence already analyzed — no spend, no overwrite
            analysis_id = row["id"]
            for kind, payload in evidence.items():
                conn.execute(
                    """
                    INSERT INTO analysis_evidence (analysis_id, kind, ref, payload)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (analysis_id, kind, kind, json.dumps(payload, default=str)),
                )
            return analysis_id

    analysis_id = await _to_thread(_write)
    return {"analysis": {**analysis, "analysis_id": analysis_id,
                         "evidence_hash": eh,
                         "already_existed": analysis_id == 0}}


def route_after_validate(state: AnalystState) -> str:
    if state.get("needs_retry") and state.get("retry_count", 0) <= 1:
        return "synthesize"
    return "persist"


def build_graph():
    g = StateGraph(AnalystState)
    g.add_node("snapshot", snapshot)
    g.add_node("gather_technical", gather_technical)
    g.add_node("gather_strategies", gather_strategies)
    g.add_node("gather_macro", gather_macro)
    g.add_node("gather_quant", gather_quant)
    g.add_node("risk", risk_node)
    g.add_node("synthesize", synthesize)
    g.add_node("validate", validate)
    g.add_node("persist", persist)

    g.add_edge(START, "snapshot")
    g.add_edge("snapshot", "gather_technical")
    g.add_edge("snapshot", "gather_strategies")
    g.add_edge("snapshot", "gather_macro")
    g.add_edge("snapshot", "gather_quant")
    g.add_edge("snapshot", "risk")
    for n in ("gather_technical", "gather_strategies", "gather_macro", "gather_quant", "risk"):
        g.add_edge(n, "synthesize")
    g.add_edge("synthesize", "validate")
    g.add_conditional_edges("validate", route_after_validate, {"synthesize": "synthesize", "persist": "persist"})
    g.add_edge("persist", END)
    return g.compile()


async def run_analysis(symbol: str, interval: str = "1day") -> dict:
    app_graph = build_graph()
    final: AnalystState = await app_graph.ainvoke(
        {"symbol": symbol.upper(), "interval": interval, "warnings": [],
         "evidence": None, "risk": None, "llm_content": None, "llm_meta": None,
         "validation_errors": [], "retry_count": 0, "analysis": None, "status": "pending"}
    )
    return {
        "symbol": final["symbol"],
        "interval": final["interval"],
        "status": final["status"],
        "analysis": final.get("analysis"),
        "risk": final.get("risk"),
        "llm_meta": final.get("llm_meta"),
        "validation_errors": final.get("validation_errors", []),
        "warnings": final.get("warnings", []),
    }
