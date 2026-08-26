"""Capacity, market-impact and crowding diagnostics for Section 23."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CapacityReport:
    strategy: str
    symbol: str
    adv_notional: float
    requested_notional: float
    participation_rate: float
    estimated_impact_bps: float
    alpha_decay: float
    crowding_score: float
    weight_multiplier: float
    accepted: bool
    reason: str


class CapacityAnalyzer:
    def __init__(self, *, max_participation_rate: float = 0.10, impact_limit_bps: float = 25.0):
        self.max_participation_rate = max_participation_rate
        self.impact_limit_bps = impact_limit_bps

    def assess(self, *, strategy: str, symbol: str, adv_notional: float, requested_notional: float, volatility: float, funding_spread_bps: float = 0.0, venue_price_convergence_bps: float = 0.0) -> CapacityReport:
        if adv_notional <= 0 or requested_notional < 0:
            raise ValueError("ADV must be positive and requested notional non-negative")
        participation = requested_notional / adv_notional
        estimated_impact = 10.0 * participation / max(1e-6, volatility or 0.01)
        alpha_decay = min(1.0, participation / max(self.max_participation_rate, 1e-9))
        crowding = min(1.0, max(0.0, abs(funding_spread_bps) / 10.0 + max(0.0, 1.0 - venue_price_convergence_bps / 10.0) * 0.5))
        multiplier = max(0.0, min(1.0, (1.0 - alpha_decay) * (1.0 - 0.5 * crowding)))
        accepted = participation <= self.max_participation_rate and estimated_impact <= self.impact_limit_bps
        reason = "capacity_within_limit" if accepted else "reduce_weight_or_reject_capacity_impact"
        return CapacityReport(strategy, symbol, adv_notional, requested_notional, participation, estimated_impact, alpha_decay, crowding, multiplier, accepted, reason)
