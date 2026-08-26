"""Read-only public cross-source market data for Section 23. No order methods."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx


@dataclass(frozen=True)
class PublicTicker:
    source: str
    symbol: str
    bid: float
    ask: float
    received_at: str
    latency_ms: float


class PublicSourceError(RuntimeError):
    pass


def _get_json(url: str, params: dict[str, str] | None = None, timeout: float = 10.0) -> tuple[object, float]:
    started = __import__("time").perf_counter()
    with httpx.Client(timeout=timeout) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
    return response.json(), (__import__("time").perf_counter() - started) * 1000.0


def fetch_coinbase_ticker(symbol: str = "BTC-USD", *, timeout: float = 10.0) -> PublicTicker:
    payload, latency = _get_json(f"https://api.exchange.coinbase.com/products/{symbol}/ticker", timeout=timeout)
    if not isinstance(payload, dict):
        raise PublicSourceError("Coinbase ticker payload is not an object")
    return PublicTicker("coinbase", symbol, float(payload["bid" ]), float(payload["ask"]), datetime.now(timezone.utc).isoformat(), latency)


def fetch_kraken_ticker(pair: str = "XBTUSD", *, timeout: float = 10.0) -> PublicTicker:
    payload, latency = _get_json("https://api.kraken.com/0/public/Ticker", {"pair": pair}, timeout)
    if not isinstance(payload, dict) or payload.get("error"):
        raise PublicSourceError(f"Kraken ticker error: {payload.get('error') if isinstance(payload, dict) else 'invalid payload'}")
    result = payload.get("result", {})
    item = next(iter(result.values()), None)
    if not item:
        raise PublicSourceError("Kraken ticker result is empty")
    return PublicTicker("kraken", pair, float(item["b"][0]), float(item["a"][0]), datetime.now(timezone.utc).isoformat(), latency)
