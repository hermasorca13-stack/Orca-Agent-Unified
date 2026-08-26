"""Section 24: temporal, geographic and multilingual event context.

This module is intentionally context/risk-only. It does not create orders or
bypass Sections 7, 10, 11, 20, 21, 22 or 23.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from hashlib import sha256
import re
from typing import Iterable
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx


@dataclass(frozen=True)
class MarketSession:
    name: str
    timezone_name: str
    open_local: time
    close_local: time
    currencies: tuple[str, ...]


DEFAULT_SESSIONS = (
    MarketSession("sydney", "Australia/Sydney", time(8, 0), time(17, 0), ("AUD", "NZD")),
    MarketSession("tokyo", "Asia/Tokyo", time(9, 0), time(18, 0), ("JPY",)),
    MarketSession("london", "Europe/London", time(8, 0), time(17, 0), ("GBP", "EUR", "CHF")),
    MarketSession("new_york", "America/New_York", time(8, 0), time(17, 0), ("USD", "CAD")),
)


@dataclass(frozen=True)
class SessionState:
    name: str
    local_time: str
    utc_offset: str
    open: bool
    currencies: tuple[str, ...]
    reason: str


class MarketClock:
    def __init__(self, sessions: tuple[MarketSession, ...] = DEFAULT_SESSIONS):
        self.sessions = sessions

    def states(self, now: datetime | None = None) -> tuple[SessionState, ...]:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        states: list[SessionState] = []
        for session in self.sessions:
            local = now.astimezone(ZoneInfo(session.timezone_name))
            is_open = local.weekday() < 5 and session.open_local <= local.time() < session.close_local
            states.append(SessionState(session.name, local.isoformat(), local.strftime("%z"), is_open, session.currencies, "open" if is_open else "closed_or_weekend"))
        return tuple(states)

    def overlap(self, now: datetime | None = None) -> tuple[str, ...]:
        return tuple(state.name for state in self.states(now) if state.open)


@dataclass(frozen=True)
class EconomicEvent:
    event_id: str
    source: str
    title: str
    category: str
    impact: str
    scheduled_at: datetime
    location: str
    language: str
    source_url: str
    retrieved_at: datetime
    surprise: float | None = None

    @property
    def fingerprint(self) -> str:
        raw = "|".join((self.source, self.title.lower().strip(), self.scheduled_at.isoformat(), self.location.lower()))
        return sha256(raw.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True)
class GdeltArticle:
    url: str
    title: str
    source_country: str
    language: str
    published_at: datetime | None
    tone: float | None
    retrieved_at: datetime


class GdeltPublicClient:
    """Read-only GDELT DOC API client; failures degrade to an empty result."""

    endpoint = "https://api.gdeltproject.org/api/v2/doc/doc"

    def search(self, query: str, *, max_records: int = 25, timeout: float = 20.0) -> tuple[GdeltArticle, ...]:
        params = {"query": query, "mode": "ArtList", "maxrecords": str(min(max_records, 250)), "format": "json", "sort": "HybridRel"}
        retrieved = datetime.now(timezone.utc)
        with httpx.Client(timeout=timeout, headers={"User-Agent": "ORCA-Max-Mouny/24 read-only"}) as client:
            response = client.get(self.endpoint, params=params)
            response.raise_for_status()
            payload = response.json()
        articles: list[GdeltArticle] = []
        for item in payload.get("articles", []) if isinstance(payload, dict) else []:
            published = None
            raw_date = item.get("seendate") or item.get("published")
            if raw_date:
                try:
                    published = datetime.strptime(str(raw_date)[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
                except ValueError:
                    published = None
            tone = None
            if item.get("tone") is not None:
                try:
                    tone = float(item["tone"])
                except (TypeError, ValueError):
                    tone = None
            articles.append(GdeltArticle(str(item.get("url", "")), str(item.get("title", "")), str(item.get("sourcecountry", "")), str(item.get("language", "")), published, tone, retrieved))
        return tuple(articles)


_POSITIVE = {
    "en": {"growth", "recovery", "strong", "deal", "peace", "support", "surplus", "easing"},
    "ar": {"نمو", "تعافي", "قوي", "سلام", "دعم", "فائض", "تيسير"},
    "es": {"crecimiento", "recuperación", "fuerte", "paz", "apoyo"},
    "fr": {"croissance", "reprise", "fort", "paix", "soutien"},
    "de": {"wachstum", "erholung", "stark", "frieden", "unterstützung"},
    "pt": {"crescimento", "recuperação", "forte", "paz", "apoio"},
    "tr": {"büyüme", "toparlanma", "güçlü", "barış", "destek"},
    "ru": {"рост", "восстановление", "сильный", "мир", "поддержка"},
    "zh": {"增长", "复苏", "强劲", "和平", "支持"},
    "ja": {"成長", "回復", "強い", "平和", "支持"},
}
_NEGATIVE = {
    "en": {"war", "crisis", "inflation", "recession", "sanction", "attack", "collapse", "default", "hawkish"},
    "ar": {"حرب", "أزمة", "تضخم", "ركود", "عقوبات", "هجوم", "انهيار", "تعثر"},
    "es": {"guerra", "crisis", "inflación", "recesión", "sanción", "ataque", "colapso"},
    "fr": {"guerre", "crise", "inflation", "récession", "sanction", "attaque", "effondrement"},
    "de": {"krieg", "krise", "inflation", "rezession", "sanktion", "angriff", "kollaps"},
    "pt": {"guerra", "crise", "inflação", "recessão", "sanção", "ataque", "colapso"},
    "tr": {"savaş", "kriz", "enflasyon", "durgunluk", "yaptırım", "saldırı", "çöküş"},
    "ru": {"война", "кризис", "инфляция", "рецессия", "санкции", "атака", "крах"},
    "zh": {"战争", "危机", "通胀", "衰退", "制裁", "攻击", "崩溃"},
    "ja": {"戦争", "危機", "インフレ", "不況", "制裁", "攻撃", "崩壊"},
}


@dataclass(frozen=True)
class SentimentResult:
    language: str
    score: float
    positive_hits: int
    negative_hits: int
    coverage: str
    source_tone: float | None


class MultilingualSentiment:
    def analyze(self, text: str, *, language: str = "", source_tone: float | None = None) -> SentimentResult:
        normalized_language = (language or "").lower().split("-")[0]
        tokens = set(re.findall(r"[^\W\d_]+", text.lower(), flags=re.UNICODE))
        positive = len(tokens & _POSITIVE.get(normalized_language, set()))
        negative = len(tokens & _NEGATIVE.get(normalized_language, set()))
        lexicon_score = (positive - negative) / max(1, positive + negative)
        if source_tone is not None:
            score = max(-1.0, min(1.0, float(source_tone) / 10.0))
            coverage = "source_tone_plus_lexicon" if normalized_language in _POSITIVE else "source_tone_only"
        else:
            score = lexicon_score
            coverage = "lexicon" if normalized_language in _POSITIVE else "unsupported_language_neutral_fallback"
        return SentimentResult(normalized_language or "unknown", score, positive, negative, coverage, source_tone)


@dataclass(frozen=True)
class CurrencyImpact:
    currency: str
    direction: str
    score: float
    confidence: float
    rationale: str


_CATEGORY_MAP = {
    "monetary_policy": ("USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD"),
    "inflation": ("USD", "EUR", "GBP", "JPY"),
    "geopolitics": ("USD", "CHF", "JPY", "EUR"),
    "employment": ("USD", "CAD", "AUD", "GBP"),
    "fiscal": ("USD", "EUR", "GBP"),
    "social": ("USD", "EUR", "GBP", "JPY"),
}


def map_event_to_currencies(event: EconomicEvent, sentiment: SentimentResult) -> tuple[CurrencyImpact, ...]:
    currencies = _CATEGORY_MAP.get(event.category, ("USD", "EUR", "JPY"))
    magnitude = {"high": 1.0, "medium": 0.6, "low": 0.25}.get(event.impact.lower(), 0.4)
    score = max(-1.0, min(1.0, sentiment.score * magnitude))
    direction = "positive_context" if score > 0.05 else "negative_context" if score < -0.05 else "neutral_uncertain"
    confidence = min(0.95, max(0.05, magnitude * (0.8 if sentiment.coverage != "unsupported_language_neutral_fallback" else 0.2)))
    return tuple(CurrencyImpact(currency, direction, score, confidence, f"event_category={event.category};impact={event.impact};language={sentiment.language}") for currency in currencies)


@dataclass(frozen=True)
class EventRiskDecision:
    allow_new_risk: bool
    risk_multiplier: float
    lock_reason: str
    active_sessions: tuple[str, ...]
    impacts: tuple[CurrencyImpact, ...]


class Section24Layer:
    def __init__(self, *, clock: MarketClock | None = None, sentiment: MultilingualSentiment | None = None):
        self.clock = clock or MarketClock()
        self.sentiment = sentiment or MultilingualSentiment()
        self.halted = False
        self.events: dict[str, EconomicEvent] = {}

    def add_event(self, event: EconomicEvent) -> str:
        self.events[event.fingerprint] = event
        return event.fingerprint

    def halt(self) -> None:
        self.halted = True

    def assess(self, *, now: datetime | None = None, currency: str = "USD", event_lock_minutes: int = 30) -> EventRiskDecision:
        now = now or datetime.now(timezone.utc)
        impacts: list[CurrencyImpact] = []
        reasons: list[str] = []
        multiplier = 1.0
        for event in self.events.values():
            until = event.scheduled_at - timedelta(minutes=event_lock_minutes)
            if until <= now <= event.scheduled_at + timedelta(minutes=event_lock_minutes):
                sentiment = self.sentiment.analyze(event.title, language=event.language)
                event_impacts = map_event_to_currencies(event, sentiment)
                impacts.extend(item for item in event_impacts if item.currency == currency)
                if event.impact.lower() == "high":
                    multiplier = min(multiplier, 0.5)
                    reasons.append(f"high_impact_event:{event.event_id}")
                elif event.impact.lower() == "medium":
                    multiplier = min(multiplier, 0.75)
                    reasons.append(f"medium_impact_event:{event.event_id}")
        if self.halted:
            return EventRiskDecision(False, 0.0, "section24_halted", self.clock.overlap(now), tuple(impacts))
        if reasons:
            return EventRiskDecision(False, multiplier, ";".join(reasons), self.clock.overlap(now), tuple(impacts))
        return EventRiskDecision(True, multiplier, "no_event_lock", self.clock.overlap(now), tuple(impacts))
