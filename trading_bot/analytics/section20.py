"""Unified adaptive layer for section 20 feedback and promotion gates."""
from __future__ import annotations

from dataclasses import dataclass, field

from trading_bot.analytics.execution_feedback import ExecutionFeedback
from trading_bot.analytics.governance21 import GovernanceDecision, Section21Governance
from trading_bot.analytics.section22 import Section22Layer, Section22TradeResult
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
    last_section21_decision: GovernanceDecision | None = None
    last_section22_trade: Section22TradeResult | None = None


class Section20Layer:
    def __init__(self, *, allocator: DynamicAllocator | None = None, feedback: ExecutionFeedback | None = None):
        self.allocator = allocator or DynamicAllocator()
        self.feedback = feedback or ExecutionFeedback()
        self.state = AdaptiveState()
        self.section21_governance = Section21Governance()
        self.section22 = Section22Layer()

    def on_closed_trade(self, *, exchange: str, symbol: str, expected_price: float, fill, strategy: str, window: PerformanceWindow, base_cost: CostEstimate, section22_features: tuple[float, ...] | list[float] | None = None, realized_pnl: float | None = None, risk_budget: float | None = None, expected_edge: float | None = None, network_stress: bool = False) -> tuple[CostEstimate, tuple[WeightDecision, ...]]:
        if section22_features is not None and realized_pnl is not None and risk_budget is not None and expected_edge is not None:
            self.on_section22_trade_closed(features=section22_features, pnl=realized_pnl, risk_budget=risk_budget, expected_edge=expected_edge, network_stress=network_stress)
        self.feedback.record(exchange=exchange, symbol=symbol, expected_price=expected_price, fill=fill)
        weights, decisions = self.allocator.allocate([window], self.state.weights)
        self.state.weights.update(weights)
        self.state.retired[f"{strategy}:{symbol}"] = evaluate_retirement(f"{strategy}:{symbol}", previous_weight=self.state.weights.get(strategy, 0.0), win_rate=window.win_rate, sharpe=window.sharpe, pbo=0.0, consecutive_bad_windows=0)
        return self.feedback.update_cost(exchange, symbol, base_cost, notional=fill.amount * fill.price), decisions

    def set_regime(self, snapshot: RegimeSnapshot) -> None:
        self.state.last_regime = snapshot

    def on_section22_trade_closed(self, *, features: tuple[float, ...] | list[float], pnl: float, risk_budget: float, expected_edge: float, network_stress: bool = False) -> Section22TradeResult:
        result = self.section22.on_trade_closed(features=features, pnl=pnl, risk_budget=risk_budget, expected_edge=expected_edge, network_stress=network_stress)
        self.state.last_section22_trade = result
        return result

    def section21_gate(self, **checks) -> GovernanceDecision:
        decision = self.section21_governance.evaluate(**checks)
        self.state.last_section21_decision = decision
        return decision

    def shadow_gate(self, *, shadow_win_rate: float, backtest_win_rate: float, shadow_pnl: float, backtest_pnl: float, shadow_trades: int) -> ShadowGate:
        gate = compare_shadow_to_backtest(shadow_win_rate=shadow_win_rate, backtest_win_rate=backtest_win_rate, shadow_pnl=shadow_pnl, backtest_pnl=backtest_pnl, shadow_trades=shadow_trades)
        self.state.last_shadow_gate = gate
        return gate
