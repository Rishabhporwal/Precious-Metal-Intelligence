"""News ingestion via RSS/Atom feeds (provider-independent, no key needed).

Security rule from the master spec: retrieved news is UNTRUSTED INPUT. We store
only parsed metadata (title/link/summary/published). No scripts/HTML is ever
executed from feed content; summaries are truncated and stored as text.
Sentiment classification is NOT done here — it lands in Phase 7 (LLM) and the
`classified` flag stays false until then. No impact claims are generated without
evidence.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

logger = logging.getLogger("news")

# Gold/macro-relevant feeds (public RSS)
FEEDS = {
    "yahoo_gold": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=GC=F&region=US&lang=en-US",
    "yahoo_silver": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=SI=F&region=US&lang=en-US",
    "yahoo_usd": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=DX-Y.NYB&region=US&lang=en-US",
}

_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    return _TAG_RE.sub("", text).strip()[:2000] or None


def _parse_published(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def fetch_feed(name: str, url: str, timeout_s: float = 15.0) -> list[dict]:
    """Fetch and parse an RSS 2.0 feed into article dicts."""
    resp = httpx.get(url, timeout=timeout_s, headers={"user-agent": "PMI-News/0.1"})
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    items = root.findall(".//item")
    out = []
    for item in items:
        title = _clean(item.findtext("title"))
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        out.append({
            "source": name,
            "url": link[:1024],
            "title": title[:512],
            "summary": _clean(item.findtext("description")),
            "published_at": _parse_published(item.findtext("pubDate")),
        })
    return out


def fetch_all_news(limit_per_feed: int = 20) -> list[dict]:
    rows: list[dict] = []
    for name, url in FEEDS.items():
        try:
            articles = fetch_feed(name, url)
        except Exception as exc:  # noqa: BLE001 — per-feed isolation
            logger.warning("news feed %s failed: %s", name, exc)
            continue
        rows.extend(articles[:limit_per_feed])
    return rows
