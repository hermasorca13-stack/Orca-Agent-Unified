"""Deterministic paper exchange for development, backtests and smoke tests."""
from __future__ import annotations

import itertools
import random
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Sequence

from trading_bot.adapters.base import ExchangeAdapter
from trading_bot.models import Fill, MarketQuote, OrderRequest, Position, Side


class PaperExchange(ExchangeAdapter):
    def __init__(self, name: str = "paper", starting_cash: float = 100_000.0, fee_bps: float = 4.0, seed: int = 7):
        self.name = name
        self.cash = float(starting_cash)
        self.fee_bps = float(fee_bps)
        self._rng = random.Random(seed)
        self._orders = []
        self._positions: dict[str, Position] = {}
        self._counter = itertools.count(1)
        self._quotes: dict[str, MarketQuote] = {}

    def set_quote(self, quote: MarketQuote) -> None:
        self._quotes[quote.symbol] = quote

    def fetch_quote(self, symbol: str) -> MarketQuote:
        quote = self._quotes.get(symbol)
        if quote is not None:
            return quote
        base = 100.0 if symbol.upper().startswith("ETH") else 1000.0
        mid = base * (1.0 + self._rng.uniform(-0.002, 0.002))
        return MarketQuote(self.name, symbol, mid - 0.05, mid + 0.05, timestamp=datetime.now(timezone.utc))

    def fetch_balance(self) -> dict[str, float]:
        used = sum(position.notional / max(position.leverage, 1.0) for position in self._positions.values())
        return {"USD": self.cash, "total": self.cash + used, "free": max(self.cash - used, 0.0), "used": used}

    def create_order(self, request: OrderRequest) -> Fill:
        quote = self.fetch_quote(request.symbol)
        price = request.price or (quote.ask if request.side == Side.BUY else quote.bid)
        notional = abs(price * request.amount)
        fee = notional * self.fee_bps / 10_000.0
        if request.side == Side.BUY:
            self.cash -= notional + fee
        else:
            self.cash += notional - fee
        order_id = request.client_order_id or f"paper-{next(self._counter):08d}"
        fill = Fill(order_id, self.name, request.symbol, request.side, request.amount, price, fee, "USD")
        if request.reduce_only:
            self._reduce_position(request, price)
        else:
            self._open_position(request, price)
        self._orders.append(fill)
        return fill

    def _open_position(self, request: OrderRequest, price: float) -> None:
        current = self._positions.get(request.symbol)
        signed = request.amount if request.side == Side.BUY else -request.amount
        if current is None:
            self._positions[request.symbol] = Position(self.name, request.symbol, request.side, signed, price, price, strategy=request.strategy)
            return
        total_amount = current.amount + signed
        if abs(total_amount) < 1e-12:
            self._positions.pop(request.symbol, None)
            return
        current.mark_price = price
        current.entry_price = (current.entry_price * abs(current.amount) + price * abs(signed)) / abs(total_amount)
        current.amount = total_amount

    def _reduce_position(self, request: OrderRequest, price: float) -> None:
        current = self._positions.get(request.symbol)
        if current is None:
            return
        signed_close = -request.amount if request.side == Side.BUY else request.amount
        current.amount += signed_close
        current.mark_price = price
        if abs(current.amount) < 1e-12:
            self._positions.pop(request.symbol, None)

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        return False

    def fetch_open_orders(self, symbol: str | None = None) -> Sequence[dict[str, Any]]:
        return []

    def fetch_positions(self) -> Sequence[dict[str, Any]]:
        return [position.__dict__.copy() for position in self._positions.values()]

    def health(self) -> dict[str, Any]:
        return {"exchange": self.name, "ok": True, "mode": "paper", "latency_ms": 0.0}
