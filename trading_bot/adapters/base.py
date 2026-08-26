"""Exchange adapter contract used by paper, sandbox and live implementations."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from trading_bot.models import Fill, MarketQuote, OrderRequest


class ExchangeAdapter(ABC):
    name: str

    @abstractmethod
    def fetch_quote(self, symbol: str) -> MarketQuote:
        raise NotImplementedError

    @abstractmethod
    def fetch_balance(self) -> dict[str, float]:
        raise NotImplementedError

    @abstractmethod
    def create_order(self, request: OrderRequest) -> Fill:
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, order_id: str, symbol: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def fetch_open_orders(self, symbol: str | None = None) -> Sequence[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def fetch_positions(self) -> Sequence[dict[str, Any]]:
        raise NotImplementedError

    def health(self) -> dict[str, Any]:
        return {"exchange": self.name, "ok": True}
