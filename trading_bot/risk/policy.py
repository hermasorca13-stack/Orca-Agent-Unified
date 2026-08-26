"""Portfolio-level policies that do not depend on a specific exchange."""
from __future__ import annotations

from dataclasses import dataclass

from trading_bot.config.settings import Settings
from trading_bot.models import Position, Side


@dataclass(frozen=True)
class PortfolioState:
    equity: float
    reserve_outside_pct: float
    gross_exposure: float
    net_exposure: float
    directional_exposure: float
    monthly_loss_pct: float
    weekly_loss_pct: float
    consecutive_losses: int


class PortfolioPolicy:
    def __init__(self, settings: Settings):
        self.settings = settings

    def violations(self, state: PortfolioState) -> tuple[str, ...]:
        violations: list[str] = []
        if state.reserve_outside_pct < self.settings.external_reserve_pct:
            violations.append("external_stablecoin_reserve_below_20_percent")
        if state.monthly_loss_pct >= self.settings.max_monthly_loss_pct:
            violations.append("monthly_loss_limit")
        if state.weekly_loss_pct >= self.settings.max_monthly_loss_pct:
            violations.append("weekly_loss_limit")
        if state.consecutive_losses >= 3:
            violations.append("mandatory_review_after_three_losses")
        if abs(state.directional_exposure) > 0 and abs(state.net_exposure) > 0:
            violations.append("directional_exposure_not_neutralized")
        return tuple(violations)

    def require_hedge(self, positions: list[Position]) -> bool:
        signed = sum((position.amount if position.side == Side.BUY else -position.amount) for position in positions)
        return abs(signed) < 1e-8

    def prohibit_martingale(self, previous_loss: bool, next_amount: float, previous_amount: float) -> bool:
        return bool(previous_loss and next_amount > previous_amount)
