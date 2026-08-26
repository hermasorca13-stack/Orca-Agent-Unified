"""Optional CCXT adapter for exchange sandbox/live connectivity.

The adapter is never instantiated by default; paper mode is the safe default.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Sequence

from trading_bot.adapters.base import ExchangeAdapter
from trading_bot.models import Fill, MarketQuote, OrderRequest, OrderType, Side


class CcxtUnavailable(RuntimeError):
    pass


class CcxtExchange(ExchangeAdapter):
    def __init__(self, name: str, api_key: str, api_secret: str, *, password: str = "", uid: str = "", sandbox: bool = True):
        try:
            import ccxt  # type: ignore
        except ImportError as exc:
            raise CcxtUnavailable("install ccxt to enable sandbox/live exchange connectivity") from exc
        if not api_key or not api_secret:
            raise ValueError(f"missing API credentials for {name}")
        self.name = name
        self._ccxt = ccxt
        exchange_cls = getattr(ccxt, name, None)
        if exchange_cls is None:
            raise ValueError(f"unsupported CCXT exchange: {name}")
        self.exchange = exchange_cls({
            "apiKey": api_key,
            "secret": api_secret,
            "password": password,
            "uid": uid,
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        })
        # CCXT requires this to be the first call after construction.
        self.exchange.set_sandbox_mode(bool(sandbox))
        self.sandbox = bool(sandbox)
        self.exchange.load_markets()

    def fetch_quote(self, symbol: str) -> MarketQuote:
        started = time.perf_counter()
        ticker = self.exchange.fetch_ticker(symbol)
        latency = (time.perf_counter() - started) * 1000.0
        return MarketQuote(
            exchange=self.name,
            symbol=symbol,
            bid=float(ticker.get("bid") or 0.0),
            ask=float(ticker.get("ask") or 0.0),
            bid_size=float(ticker.get("bidVolume") or 0.0),
            ask_size=float(ticker.get("askVolume") or 0.0),
            timestamp=datetime.fromtimestamp(float(ticker.get("timestamp") or time.time() * 1000) / 1000.0, timezone.utc),
            funding_rate=0.0,
            open_interest=0.0,
            volume_24h=float(ticker.get("quoteVolume") or 0.0),
            latency_ms=latency,
        )

    def fetch_balance(self) -> dict[str, float]:
        balance = self.exchange.fetch_balance()
        total = sum(float(value or 0.0) for value in balance.get("total", {}).values())
        free = sum(float(value or 0.0) for value in balance.get("free", {}).values())
        used = sum(float(value or 0.0) for value in balance.get("used", {}).values())
        return {"total": total, "free": free, "used": used}

    def create_order(self, request: OrderRequest) -> Fill:
        if request.order_type == OrderType.STOP_LIMIT:
            raise NotImplementedError("stop-limit parameters are exchange-specific; use a dedicated adapter extension")
        order = self.exchange.create_order(
            request.symbol,
            request.order_type.value,
            request.side.value,
            request.amount,
            request.price,
            {"reduceOnly": request.reduce_only},
        )
        filled = float(order.get("filled") or request.amount)
        average = float(order.get("average") or request.price or 0.0)
        fee_info = order.get("fee") or {}
        return Fill(
            order_id=str(order.get("id") or uuid.uuid4()),
            exchange=self.name,
            symbol=request.symbol,
            side=request.side,
            amount=filled,
            price=average,
            fee=float(fee_info.get("cost") or 0.0),
            fee_currency=str(fee_info.get("currency") or ""),
            status=str(order.get("status") or "open"),
        )

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        self.exchange.cancel_order(order_id, symbol)
        return True

    def fetch_open_orders(self, symbol: str | None = None) -> Sequence[dict[str, Any]]:
        return self.exchange.fetch_open_orders(symbol)

    def fetch_positions(self) -> Sequence[dict[str, Any]]:
        method = getattr(self.exchange, "fetch_positions", None)
        return method() if method else []

    def health(self) -> dict[str, Any]:
        return {"exchange": self.name, "ok": True, "sandbox": self.sandbox}
