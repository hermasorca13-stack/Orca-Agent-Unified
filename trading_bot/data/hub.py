"""Market-data orchestration and freshness monitoring."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from trading_bot.data.providers import BinancePublicProvider, ProviderError
from trading_bot.models import MarketQuote
from trading_bot.storage.market_store import MarketStore


class MarketDataHub:
    def __init__(self, provider: BinancePublicProvider, store: MarketStore, *, max_age_seconds: float = 3.0, max_latency_ms: float = 500.0):
        self.provider = provider
        self.store = store
        self.max_age_seconds = max_age_seconds
        self.max_latency_ms = max_latency_ms
        self.last_quotes: dict[tuple[str, str], MarketQuote] = {}

    def snapshot(self, symbols: Iterable[str]) -> list[MarketQuote]:
        quotes = []
        for symbol in symbols:
            quote = self.provider.fetch_quote(symbol)
            self.store.record_quote(quote)
            self.last_quotes[(quote.exchange, quote.symbol)] = quote
            quotes.append(quote)
        return quotes

    def health(self) -> dict[str, object]:
        now = datetime.now(timezone.utc)
        stale = []
        slow = []
        for key, quote in self.last_quotes.items():
            age = (now - quote.timestamp).total_seconds()
            if age > self.max_age_seconds:
                stale.append({"exchange": key[0], "symbol": key[1], "age_seconds": age})
            if quote.latency_ms > self.max_latency_ms:
                slow.append({"exchange": key[0], "symbol": key[1], "latency_ms": quote.latency_ms})
        return {"ok": not stale and not slow, "stale": stale, "slow": slow, "quotes": len(self.last_quotes)}

    async def stream(self, symbols: Iterable[str]):
        async for quote in self.provider.stream_quotes(symbols):
            self.store.record_quote(quote)
            self.last_quotes[(quote.exchange, quote.symbol)] = quote
            yield quote
