"""Macro/news/calendar persistence."""

from __future__ import annotations

import json
from datetime import date

from app.db import get_pool


def _to_date(d) -> date:
    if isinstance(d, date):
        return d
    return date.fromisoformat(str(d)[:10])


def insert_macro_observations(rows: list[dict]) -> int:
    written = 0
    with get_pool().connection() as conn:
        for r in rows:
            cur = conn.execute(
                """
                INSERT INTO macro_observations
                    (provider, series_id, title, units, as_of_date, value, meta)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (provider, series_id, as_of_date, fetched_at) DO NOTHING
                """,
                (r["provider"], r["series_id"], r.get("title"), r.get("units"),
                 _to_date(r["as_of_date"]), r.get("value"), json.dumps(r.get("meta", {}), default=str)),
            )
            written += cur.rowcount
    return written


def insert_economic_events(events: list[dict]) -> int:
    written = 0
    with get_pool().connection() as conn:
        for e in events:
            cur = conn.execute(
                """
                INSERT INTO economic_events
                    (source, release_name, series_id, event_date, actual_value, units)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (source, release_name, coalesce(series_id, ''), event_date)
                DO UPDATE SET actual_value = EXCLUDED.actual_value, units = EXCLUDED.units
                """,
                (e["source"], e["release_name"], e.get("series_id"),
                 _to_date(e["event_date"]), e.get("actual_value"), e.get("units")),
            )
            written += cur.rowcount
    return written


def insert_news(articles: list[dict]) -> int:
    written = 0
    with get_pool().connection() as conn:
        for a in articles:
            cur = conn.execute(
                """
                INSERT INTO news_articles
                    (source, url, title, summary, published_at, classified)
                VALUES (%s, %s, %s, %s, %s, false)
                ON CONFLICT (url) DO NOTHING
                """,
                (a["source"], a["url"], a["title"], a.get("summary"), a.get("published_at")),
            )
            written += cur.rowcount
    return written


def macro_series_summary() -> list[dict]:
    """Latest + previous observation per series (for deltas)."""
    with get_pool().connection() as conn:
        cur = conn.execute(
            """
            SELECT DISTINCT ON (series_id)
                series_id, title, units, as_of_date, value, fetched_at
            FROM macro_observations
            WHERE provider = 'fred'
            ORDER BY series_id, as_of_date DESC, fetched_at DESC
            """
        )
        latest = cur.fetchall()
        out = []
        for row in latest:
            prev = conn.execute(
                """
                SELECT value, as_of_date FROM macro_observations
                WHERE provider = 'fred' AND series_id = %s AND as_of_date < %s
                ORDER BY as_of_date DESC LIMIT 1
                """,
                (row["series_id"], row["as_of_date"]),
            ).fetchone()
            change = None
            if prev and prev["value"] is not None and row["value"] is not None:
                change = row["value"] - prev["value"]
            out.append({**row, "previous_value": prev["value"] if prev else None,
                        "previous_date": prev["as_of_date"] if prev else None,
                        "change": change})
        return out


def cftc_positioning() -> list[dict]:
    with get_pool().connection() as conn:
        cur = conn.execute(
            """
            SELECT DISTINCT ON (series_id)
                series_id, title, as_of_date, value, meta
            FROM macro_observations
            WHERE provider = 'cftc'
            ORDER BY series_id, as_of_date DESC
            """
        )
        return cur.fetchall()


def upcoming_events(days_ahead: int = 30, past_days: int = 14) -> list[dict]:
    with get_pool().connection() as conn:
        cur = conn.execute(
            """
            SELECT release_name, series_id, event_date, actual_value, units
            FROM economic_events
            WHERE event_date >= CURRENT_DATE - %s AND event_date <= CURRENT_DATE + %s
            ORDER BY event_date
            """,
            (past_days, days_ahead),
        )
        return cur.fetchall()


def latest_news(limit: int = 20) -> list[dict]:
    with get_pool().connection() as conn:
        cur = conn.execute(
            """
            SELECT source, url, title, summary, published_at, fetched_at, classified, sentiment
            FROM news_articles
            ORDER BY COALESCE(published_at, fetched_at) DESC
            LIMIT %s
            """,
            (limit,),
        )
        return cur.fetchall()
