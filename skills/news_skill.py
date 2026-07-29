"""
skills/news_skill.py — News headlines via Google News RSS (no API key).

Why this skill:
- Google retired the official News API in 2011. The Google News RSS
  feeds at `news.google.com/rss/...` are the only free, no-key,
  live-data route in 2026. They return clean XML; we parse with the
  stdlib only (no `feedparser` dep).

Public surface:
- `search(query, limit=10)` — headlines for a search query.
- `topic(topic, limit=10)` — headlines for a topic slug
  (e.g. "TECHNOLOGY", "WORLD", "BUSINESS").
"""
from __future__ import annotations

import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import List, Tuple

UA = "Mozilla/5.0 (compatible; OrcaAgent/0.6)"

_BASE = "https://news.google.com/rss"

# Known topics. Slugs match Google's `section/topic/...` paths.
TOPICS = {
    "WORLD": "WORLD",
    "NATION": "NATION",
    "BUSINESS": "BUSINESS",
    "TECHNOLOGY": "TECHNOLOGY",
    "ENTERTAINMENT": "ENTERTAINMENT",
    "SPORTS": "SPORTS",
    "SCIENCE": "SCIENCE",
    "HEALTH": "HEALTH",
}


def _fetch(url: str, timeout: float = 10.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _parse(xml_bytes: bytes) -> List[Tuple[str, str, str, str]]:
    """Return list of (title, link, pubDate, source)."""
    root = ET.fromstring(xml_bytes)
    items: List[Tuple[str, str, str, str]] = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        src_el = item.find("source")
        src = (src_el.text or "").strip() if src_el is not None else ""
        items.append((title, link, pub, src))
    return items


def _format(items: List[Tuple[str, str, str, str]], heading: str) -> str:
    if not items:
        return f"📰 No results for *{heading}*"
    lines = [f"📰 *News: {heading}*", ""]
    for i, (t, link, pub, src) in enumerate(items, 1):
        if not t:
            continue
        lines.append(f"{i}. {t}")
        meta = " — ".join(filter(None, [src, pub]))
        if meta:
            lines.append(f"   _{meta}_")
    return "\n".join(lines)


async def search(query: str, limit: int = 10) -> str:
    q = (query or "").strip()
    if not q:
        return "🔍 Empty query"
    limit = max(1, min(30, int(limit)))
    url = f"{_BASE}/search?q={urllib.parse.quote(q)}&hl=en-US&gl=US&ceid=US:en"
    try:
        xml = _fetch(url)
        items = _parse(xml)[:limit]
    except Exception as exc:  # noqa: BLE001
        return f"❌ News fetch failed: {exc}"
    return _format(items, q)


async def topic(topic: str, limit: int = 10) -> str:
    t = (topic or "").strip().upper()
    if t not in TOPICS:
        return f"⚠️ Unknown topic. Pick one of: {', '.join(TOPICS)}"
    limit = max(1, min(30, int(limit)))
    url = f"{_BASE}/headlines/section/topic/{t}?hl=en-US&gl=US&ceid=US:en"
    try:
        xml = _fetch(url)
        items = _parse(xml)[:limit]
    except Exception as exc:  # noqa: BLE001
        return f"❌ News fetch failed: {exc}"
    return _format(items, t.title())
