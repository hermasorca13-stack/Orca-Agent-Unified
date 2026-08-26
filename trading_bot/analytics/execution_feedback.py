"""Execution-quality feedback loop keyed by exchange and symbol."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

from trading_bot.models import CostEstimate, Fill, Side


@dataclass(frozen=True)
class ExecutionObservation:
    exchange: str
    symbol: str
    slippage_bps: float
    latency_ms: float
    rejected: bool = False


class ExecutionFeedback:
    def __init__(self, *, window: int = 100, assumed_slippage_bps: float = 2.0, repeated_breaches: int = 3):
        self.window = window
        self.assumed_slippage_bps = assumed_slippage_bps
        self.repeated_breaches = repeated_breaches
        self.observations: dict[tuple[str, str], deque[ExecutionObservation]] = defaultdict(lambda: deque(maxlen=self.window))

    def record(self, *, exchange: str, symbol: str, expected_price: float, fill: Fill, latency_ms: float = 0.0, rejected: bool = False) -> ExecutionObservation:
        signed = 1.0 if fill.side == Side.BUY else -1.0
        slippage_bps = signed * (fill.price - expected_price) / max(expected_price, 1e-12) * 10_000
        observation = ExecutionObservation(exchange, symbol, max(0.0, slippage_bps), latency_ms, rejected)
        self.observations[(exchange, symbol)].append(observation)
        return observation

    def stats(self, exchange: str, symbol: str) -> dict[str, float | int | bool]:
        values = list(self.observations[(exchange, symbol)])
        if not values:
            return {"observations": 0, "mean_slippage_bps": self.assumed_slippage_bps, "reject_rate": 0.0, "suspended": False}
        mean = sum(value.slippage_bps for value in values) / len(values)
        reject_rate = sum(value.rejected for value in values) / len(values)
        breaches = sum(value.slippage_bps > self.assumed_slippage_bps for value in values[-self.repeated_breaches:])
        return {"observations": len(values), "mean_slippage_bps": mean, "reject_rate": reject_rate, "suspended": breaches >= self.repeated_breaches}

    def update_cost(self, exchange: str, symbol: str, base: CostEstimate, *, notional: float = 100_000.0) -> CostEstimate:
        stats = self.stats(exchange, symbol)
        observed_cash = notional * float(stats["mean_slippage_bps"]) / 10_000.0
        return CostEstimate(base.fees, base.spread, observed_cash, base.funding, base.borrow, base.transfer, base.gas)

    def rank_venues(self, symbol: str, exchanges: list[str]) -> list[str]:
        return sorted(exchanges, key=lambda exchange: (bool(self.stats(exchange, symbol)["suspended"]), float(self.stats(exchange, symbol)["mean_slippage_bps"]), float(self.stats(exchange, symbol)["reject_rate"])) )
