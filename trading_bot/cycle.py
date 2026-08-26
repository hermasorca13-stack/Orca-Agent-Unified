"""Single-cycle orchestration for market data -> signal -> risk -> execution."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from trading_bot.adapters.base import ExchangeAdapter
from trading_bot.data.context import MarketContextProvider
from trading_bot.models import CostEstimate, RiskSnapshot, Signal
from trading_bot.risk.gates import MarketContext, RiskEngine
from trading_bot.storage.audit import AuditLog


@dataclass(frozen=True)
class CycleResult:
    signal: Signal | None
    allowed: bool
    code: str
    reasons: tuple[str, ...]
    fills: int = 0


class TradingCycle:
    def __init__(self, adapter: ExchangeAdapter, risk: RiskEngine, audit: AuditLog, *, context_provider: MarketContextProvider | None = None):
        self.adapter = adapter
        self.risk = risk
        self.audit = audit
        self.context_provider = context_provider

    def evaluate(self, symbol: str, signal_fn: Callable[[str], Signal | None], snapshot: RiskSnapshot, costs: CostEstimate, context: MarketContext | None = None) -> CycleResult:
        signal = signal_fn(symbol)
        if signal is None:
            self.audit.write("signal_rejected", {"symbol": symbol, "reason": "no_signal"})
            return CycleResult(None, False, "NO_SIGNAL", ("no_signal",))
        context = context or MarketContext()
        gate = self.risk.trade_gate(signal, context, snapshot, costs)
        self.audit.write("risk_gate", {"signal": signal, "gate": gate})
        if not gate.allowed:
            return CycleResult(signal, False, gate.code, gate.reasons)
        return CycleResult(signal, True, gate.code, gate.reasons)
