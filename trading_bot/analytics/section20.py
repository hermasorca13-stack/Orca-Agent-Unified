"""Unified adaptive layer for section 20 feedback and promotion gates."""
from __future__ import annotations

from dataclasses import dataclass, field

from trading_bot.analytics.execution_feedback import ExecutionFeedback
from trading_bot.analytics.regime import RegimeSnapshot
from trading_bot.analytics.retirement import RetirementDecision, evaluate as evaluate_retirement
from trading_bot.analytics.shadow import ShadowGate, compare_shadow_to_backtest
from trading_bot.analytics.weighting import DynamicAllocator, PerformanceWindow, WeightDecision
from trading_bot.models import CostEstimate


@dataclass
class AdaptiveState:
    weights: dict[str, float] = field(default_factory=dict)
    retired: dict[str, RetirementDecision] = field(default_factory=dict)
    last_regime: RegimeSnapshot | None = None
    last_shadow_gate: ShadowGate | None = None


class Section20Layer:
    def __init__(self, *, allocator: DynamicAllocator | None = None, feedback: ExecutionFeedback | None = None):
        self.allocator = allocator or DynamicAllocator()
        self.feedback = feedback or ExecutionFeedback()
        self.state = AdaptiveState()

    def on_closed_trade(self, *, exchange: str, symbol: str, expected_price: float, fill, strategy: str, window: PerformanceWindow, base_cost: CostEstimate) -> tuple[CostEstimate, tuple[WeightDecision, ...]]:
        self.feedback.record(exchange=exchange, symbol=symbol, expected_price=expected_price, fill=fill)
        weights, decisions = self.allocator.allocate([window], self.state.weights)
        self.state.weights.update(weights)
        self.state.retired[f"{strategy}:{symbol}"] = evaluate_retirement(f"{strategy}:{symbol}", previous_weight=self.state.weights.get(strategy, 0.0), win_rate=window.win_rate, sharpe=window.sharpe, pbo=0.0, consecutive_bad_windows=0)
        return self.feedback.update_cost(exchange, symbol, base_cost, notional=fill.amount * fill.price), decisions

    def set_regime(self, snapshot: RegimeSnapshot) -> None:
        self.state.last_regime = snapshot

    def shadow_gate(self, *, shadow_win_rate: float, backtest_win_rate: float, shadow_pnl: float, backtest_pnl: float, shadow_trades: int) -> ShadowGate:
        gate = compare_shadow_to_backtest(shadow_win_rate=shadow_win_rate, backtest_win_rate=backtest_win_rate, shadow_pnl=shadow_pnl, backtest_pnl=backtest_pnl, shadow_trades=shadow_trades)
        self.state.last_shadow_gate = gate
        return gate
