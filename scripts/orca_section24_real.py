"""Section 24 read-only real-data verification using GDELT and market clocks."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from trading_bot.analytics.section24 import GdeltPublicClient, MarketClock, MultilingualSentiment
from trading_bot.analytics.rss24 import PublicRssClient

REPORT = Path("docs/section24_report_2026-08-26.json")


def main() -> dict:
    retrieved_at = datetime.now(timezone.utc)
    client = GdeltPublicClient()
    source_used = "GDELT DOC public API"
    try:
        articles = client.search("bitcoin OR cryptocurrency OR bitcoin OR criptomonedas", max_records=50, timeout=30.0)
        error = None
    except Exception as exc:
        articles = ()
        error = type(exc).__name__
    if not articles:
        source_used = "Google News RSS public fallback"
        rss_articles = PublicRssClient().search("bitcoin cryptocurrency", max_per_locale=5, timeout=15.0)
        articles_count = len(rss_articles)
        sentiments = [MultilingualSentiment().analyze(article.title, language=article.language) for article in rss_articles]
        language_counts = Counter(item.language or "unknown" for item in rss_articles)
        country_counts = Counter(item.region or "unknown" for item in rss_articles)
        article_samples = [article.__dict__ for article in rss_articles[:10]]
    else:
        articles_count = len(articles)
        sentiments = [MultilingualSentiment().analyze(article.title, language=article.language, source_tone=article.tone) for article in articles]
        language_counts = Counter(item.language or "unknown" for item in articles)
        country_counts = Counter(item.source_country or "unknown" for item in articles)
        article_samples = [article.__dict__ for article in articles[:10]]
    scores = [item.score for item in sentiments]
    article_count = articles_count
    payload = {
        "as_of": retrieved_at.isoformat(),
        "data_source": source_used,
        "query": "bitcoin OR cryptocurrency OR bitcoin OR criptomonedas",
        "articles": article_count,
        "source_error": error,
        "languages": dict(language_counts),
        "source_countries": dict(country_counts),
        "sentiment": {"mean_score": sum(scores) / len(scores) if scores else None, "min_score": min(scores) if scores else None, "max_score": max(scores) if scores else None, "method": "GDELT tone when available plus language lexicon; context-only, not causal"},
        "market_sessions": [state.__dict__ for state in MarketClock().states(retrieved_at)],
        "official_calendar_sources": [{"name": "Federal Reserve FOMC", "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", "status": "source_registered; event-specific ingestion requires calendar parser"}],
        "article_samples": article_samples,
        "execution": {"orders_submitted": 0, "keys_used": False, "live_authority": False},
        "disclosure": "News coverage and tone are media-derived context. They are not verified facts, causal estimates, or a trading signal; unsupported languages use a neutral fallback. If GDELT failed, the report explicitly identifies the RSS fallback.",
    }
    REPORT.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))
    return payload


if __name__ == "__main__":
    main()
