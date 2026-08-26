"""Public multilingual RSS fallback for Section 24."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree
from urllib.parse import quote_plus

import httpx


@dataclass(frozen=True)
class RssArticle:
    title: str
    url: str
    language: str
    region: str
    published_at: datetime | None
    source: str
    retrieved_at: datetime


DEFAULT_LOCALES = (
    ("en", "US"), ("ar", "EG"), ("es", "ES"), ("fr", "FR"),
    ("de", "DE"), ("pt", "BR"), ("tr", "TR"), ("ru", "RU"),
    ("zh-CN", "CN"), ("ja", "JP"),
)


class PublicRssClient:
    def search(self, query: str, *, locales: tuple[tuple[str, str], ...] = DEFAULT_LOCALES, max_per_locale: int = 10, timeout: float = 20.0) -> tuple[RssArticle, ...]:
        retrieved = datetime.now(timezone.utc)
        articles: list[RssArticle] = []
        for language, region in locales:
            url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl={quote_plus(language)}&gl={quote_plus(region)}&ceid={quote_plus(region + ':' + language)}"
            try:
                with httpx.Client(timeout=timeout, headers={"User-Agent": "ORCA-Max-Mouny/24 read-only"}) as client:
                    response = client.get(url)
                    response.raise_for_status()
                root = ElementTree.fromstring(response.content)
                for item in root.findall("./channel/item")[:max_per_locale]:
                    title = item.findtext("title") or ""
                    link = item.findtext("link") or ""
                    raw_date = item.findtext("pubDate")
                    published = None
                    if raw_date:
                        try:
                            published = parsedate_to_datetime(raw_date).astimezone(timezone.utc)
                        except (TypeError, ValueError, OverflowError):
                            published = None
                    if title:
                        articles.append(RssArticle(title, link, language.split("-")[0], region, published, "google_news_rss", retrieved))
            except (httpx.HTTPError, ElementTree.ParseError):
                continue
        return tuple(articles)
