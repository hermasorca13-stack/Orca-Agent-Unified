"""Live market-data providers with REST snapshots and optional WebSocket streams."""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import AsyncIterator, Iterable

import httpx

from trading_bot.models import MarketQuote


class ProviderError(RuntimeError):
    pass


class BinancePublicProvider:
    """Read-only Binance market data; no credentials and no order capability."""

    def __init__(self, *, base_url: str = "https://api.binance.com", ws_url: str = "wss://stream.binance.com:9443/stream", timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.ws_url = ws_url.rstrip("/")
        self.timeout = timeout

    def _get(self, path: str, params: dict[str, str] | None = None) -> tuple[object, float]:
        started = time.perf_counter()
        with httpx.Client(timeout=self.timeout) as client:
            url = path if path.startswith("http://") or path.startswith("https://") else f"{self.base_url}{path}"
            response = client.get(url, params=params)
            response.raise_for_status()
        latency_ms = (time.perf_counter() - started) * 1000.0
        return response.json(), latency_ms

    def fetch_quote(self, symbol: str) -> MarketQuote:
        normalized = symbol.replace("/", "").upper()
        ticker, latency_ms = self._get("/api/v3/ticker/24hr", {"symbol": normalized})
        return MarketQuote(
            exchange="binance",
            symbol=symbol,
            bid=float(ticker["bidPrice"]),
            ask=float(ticker["askPrice"]),
            bid_size=float(ticker["bidQty"]),
            ask_size=float(ticker["askQty"]),
            timestamp=datetime.now(timezone.utc),
            volume_24h=float(ticker.get("quoteVolume") or 0.0),
            latency_ms=latency_ms,
        )

    def fetch_order_book(self, symbol: str, limit: int = 20) -> dict[str, object]:
        normalized = symbol.replace("/", "").upper()
        payload, latency_ms = self._get("/api/v3/depth", {"symbol": normalized, "limit": str(limit)})
        return {"symbol": symbol, "bids": payload.get("bids", []), "asks": payload.get("asks", []), "latency_ms": latency_ms, "ts": datetime.now(timezone.utc).isoformat()}

    def fetch_ohlcv(self, symbol: str, interval: str = "1m", limit: int = 500) -> list[list[float]]:
        normalized = symbol.replace("/", "").upper()
        payload, _ = self._get("/api/v3/klines", {"symbol": normalized, "interval": interval, "limit": str(min(limit, 1000))})
        return [[float(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5])] for row in payload]

    def fetch_derivatives_context(self, symbol: str) -> dict[str, object]:
        normalized = symbol.replace("/", "").upper()
        funding, funding_latency = self._get("https://fapi.binance.com/fapi/v1/premiumIndex", {"symbol": normalized})
        oi, oi_latency = self._get("https://fapi.binance.com/fapi/v1/openInterest", {"symbol": normalized})
        return {"symbol": symbol, "funding_rate": float(funding.get("lastFundingRate") or 0.0), "open_interest": float(oi.get("openInterest") or 0.0), "latency_ms": max(funding_latency, oi_latency), "ts": datetime.now(timezone.utc).isoformat()}

    async def stream_quotes(self, symbols: Iterable[str]) -> AsyncIterator[MarketQuote]:
        try:
            import websockets  # type: ignore
        except ImportError as exc:
            raise ProviderError("install websockets to enable Binance WebSocket streaming") from exc
        streams = "/".join(f"{symbol.replace('/', '').lower()}@bookTicker" for symbol in symbols)
        async with websockets.connect(f"{self.ws_url}?streams={streams}", ping_interval=20, ping_timeout=10) as socket:
            async for raw in socket:
                message = json.loads(raw)
                payload = message.get("data", message)
                yield MarketQuote(
                    exchange="binance",
                    symbol=payload["s"],
                    bid=float(payload["b"]),
                    ask=float(payload["a"]),
                    bid_size=float(payload["B"]),
                    ask_size=float(payload["A"]),
                    timestamp=datetime.now(timezone.utc),
                )
