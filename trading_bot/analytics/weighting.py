"""Capped, gradual performance weighting for strategies and symbols."""
from __future__ import annotations

from dataclasses import dataclass
from math import exp


@dataclass(frozen=True)
class PerformanceWindow:
    key: str
    trades: int
    win_rate: float
    profit_factor: float
    sharpe: float


@dataclass(frozen=True)
class WeightDecision:
    key: str
    previous: float
    proposed: float
    reason: str


class DynamicAllocator:
    def __init__(self, *, minimum: float = 0.05, maximum: float = 0.30, step_limit: float = 0.05, lookback: int = 75):
        self.minimum = minimum
        self.maximum = maximum
        self.step_limit = step_limit
        self.lookback = lookback

    def allocate(self, windows: list[PerformanceWindow], previous: dict[str, float]) -> tuple[dict[str, float], tuple[WeightDecision, ...]]:
        if not windows:
            return {}, ()
        raw = {window.key: max(0.01, window.win_rate * max(window.profit_factor, 0.01) * max(0.25, 1.0 + window.sharpe / 4.0)) for window in windows if window.trades >= max(10, self.lookback // 3)}
        if not raw:
            return dict(previous), ()
        total = sum(raw.values())
        target = {key: min(self.maximum, max(self.minimum, value / total)) for key, value in raw.items()}
        norm = sum(target.values())
        target = {key: value / norm for key, value in target.items()}
        decisions = []
        result = dict(previous)
        for key, proposed in target.items():
            old = previous.get(key, 1.0 / len(target))
            bounded = min(old + self.step_limit, max(old - self.step_limit, proposed))
            result[key] = bounded
            decisions.append(WeightDecision(key, old, bounded, "rolling_performance_capped_gradual_rebalance"))
        total_result = sum(result.values())
        if total_result:
            result = {key: value / total_result for key, value in result.items()}
        return result, tuple(decisions)
