"""News Intelligence API: clustered global events."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.db import get_pool

router = APIRouter(prefix="/v1/news", tags=["news-intelligence"])


@router.get("/events")
def events(limit: int = Query(default=20, ge=1, le=50)) -> dict:
    with get_pool().connection() as conn:
        cur = conn.execute(
            """
            SELECT e.id, e.title, e.category, e.region, e.entities, e.importance,
                   e.gold_impact, e.verification_status, e.sources_count, e.source_names,
                   e.status, e.first_seen, e.last_update,
                   (
                     SELECT json_agg(json_build_object(
                         'title', a.title, 'source', a.source, 'url', a.url,
                         'published_at', a.published_at, 'sentiment', a.sentiment) ORDER BY a.published_at DESC)
                     FROM news_articles a WHERE a.event_id = e.id
                   ) AS articles
            FROM news_events e
            ORDER BY e.last_update DESC LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()
    return {
        "count": len(rows),
        "events": [
            {
                "id": r["id"],
                "title": r["title"],
                "category": r["category"],
                "region": r["region"],
                "entities": r["entities"],
                "importance": r["importance"],
                "gold_impact": r["gold_impact"],
                "verification": r["verification_status"],
                "sources_count": r["sources_count"],
                "sources": r["source_names"],
                "status": r["status"],
                "first_seen": r["first_seen"].isoformat() if r["first_seen"] else None,
                "last_update": r["last_update"].isoformat() if r["last_update"] else None,
                "articles": r["articles"] or [],
            }
            for r in rows
        ],
    }
