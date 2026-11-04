"""News Intelligence: event clustering + verification (enhancement spec §4).

One geopolitical event generates many articles — they must become ONE event
record, not N bullish votes (§4.3). The LLM proposes event groupings from
recent classified articles (classification is interpretation, allowed); the
storage and verification logic is deterministic.

Verification statuses (§4.2):
  CONFIRMED  — ≥2 distinct independent sources report the same event
  REPORTED   — single credible source
  DEVELOPING — event updated within the last 6 hours (details may change)
  UNVERIFIED — default until classified
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import UTC, datetime, timedelta

from app.db import get_pool

STOPWORDS = {"the", "a", "an", "of", "in", "on", "for", "to", "and", "as", "at", "with",
             "after", "over", "amid", "says", "report", "reports", "new", "us"}


def _slug(name: str) -> str:
    s = unicodedata.normalize("NFKD", name.lower())
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", "-", s.strip())[:80]


def _tokens(name: str) -> set[str]:
    return {t for t in _slug(name).split("-") if t and t not in STOPWORDS}


def _similar(a: str, b: str) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    inter = len(ta & tb)
    return inter / min(len(ta), len(tb)) >= 0.6


async def cluster_events(cfg) -> dict:
    """LLM proposes event groupings over recent classified articles; storage is ours."""
    from providers.llm import chat

    cutoff = datetime.now(UTC) - timedelta(days=7)
    with get_pool().connection() as conn:
        cur = conn.execute(
            """
            SELECT id, title, source, sentiment, published_at
            FROM news_articles
            WHERE classified = true AND COALESCE(published_at, fetched_at) >= %s
              AND event_id IS NULL
            ORDER BY COALESCE(published_at, fetched_at) DESC LIMIT 40
            """,
            (cutoff,),
        )
        articles = cur.fetchall()
        if not articles:
            return {"clustered": 0, "note": "no unclustered classified articles"}
        cur = conn.execute(
            """
            SELECT id, title, status FROM news_events
            WHERE status = 'open' AND last_update >= %s
            """,
            (datetime.now(UTC) - timedelta(days=7),),
        )
        open_events = cur.fetchall()

    payload = [
        {"i": i, "title": a["title"], "source": a["source"], "sentiment": a["sentiment"]}
        for i, a in enumerate(articles)
    ]
    messages = [
        {
            "role": "system",
            "content": (
                "You cluster gold-market news headlines into underlying EVENTS. Multiple articles"
                " about the same event MUST share one event name (canonical, short, factual)."
                " Do not invent events beyond what the headlines state. Output STRICT JSON:"
                ' [{"event": "<canonical name>", "category": "geopolitics|central_bank|economy|elections|market|other",'
                ' "region": "<region or country>", "entities": ["..."],'
                ' "importance": "high|medium|low", "gold_impact": "bullish|bearish|mixed|uncertain",'
                ' "article_ids": [<ints>]}].'
                " No prose outside JSON."
            ),
        },
        {"role": "user", "content": json.dumps(payload)},
    ]
    result = await chat(messages, cfg=cfg, max_tokens=1500)
    text = re.sub(r"^```(?:json)?\s*", "", result["content"].strip())
    text = re.sub(r"```\s*$", "", text)
    events = json.loads(text)

    article_by_index = {i: a for i, a in enumerate(articles)}
    linked = 0
    created = 0
    now = datetime.now(UTC)
    with get_pool().connection() as conn:
        for ev in events:
            name = (ev.get("event") or "").strip()
            ids = [i for i in ev.get("article_ids", []) if i in article_by_index]
            if not name or not ids:
                continue
            category = ev.get("category") if ev.get("category") in (
                "geopolitics", "central_bank", "economy", "elections", "market", "other"
            ) else "other"
            importance = ev.get("importance") if ev.get("importance") in ("high", "medium", "low") else "medium"
            gold_impact = ev.get("gold_impact") if ev.get("gold_impact") in (
                "bullish", "bearish", "mixed", "uncertain"
            ) else "uncertain"
            key = _slug(name)
            sources = sorted({article_by_index[i]["source"] for i in ids})
            if len(sources) >= 2:
                verification = "CONFIRMED"
            else:
                verification = "REPORTED"

            # match an existing open event by slug or fuzzy name overlap
            match = next((o for o in open_events if o["title"].lower() == name.lower() or _similar(o["title"], name)), None)
            if match:
                conn.execute(
                    """
                    UPDATE news_events SET last_update = %s,
                        sources_count = GREATEST(sources_count, %s),
                        source_names = %s,
                        verification_status = CASE
                            WHEN %s >= 2 THEN 'CONFIRMED'
                            ELSE verification_status END
                    WHERE id = %s
                    """,
                    (now, len(sources), json.dumps(sources), len(sources), match["id"]),
                )
                event_id = match["id"]
            else:
                cur = conn.execute(
                    """
                    INSERT INTO news_events
                        (cluster_key, title, category, region, entities, importance,
                         gold_impact, verification_status, sources_count, source_names, first_seen, last_update)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (key, name, category, ev.get("region"), json.dumps(ev.get("entities", [])),
                     importance, gold_impact, verification, len(sources), json.dumps(sources), now, now),
                )
                event_id = int(cur.fetchone()["id"])
                created += 1

            conn.execute(
                "UPDATE news_articles SET event_id = %s WHERE id = ANY(%s)",
                (event_id, [article_by_index[i]["id"] for i in ids]),
            )
            linked += len(ids)

        # DEVELOPING: events updated in the last 6 hours with multiple sources
        conn.execute(
            """
            UPDATE news_events SET verification_status = 'DEVELOPING'
            WHERE status = 'open' AND verification_status IN ('CONFIRMED', 'REPORTED')
              AND last_update >= %s AND sources_count >= 2
            """,
            (now - timedelta(hours=6),),
        )
    return {"clustered": linked, "events_created": created, "cache_hit": result.get("cache_hit", False)}
