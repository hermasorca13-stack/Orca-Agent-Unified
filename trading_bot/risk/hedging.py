"""Beta-weighted dollar-neutral hedge calculations."""
from __future__ import annotations

from dataclasses import dataclass

from trading_bot.models import Position, Side


@dataclass(frozen=True)
class HedgePlan:
    base_symbol: str
    hedge_symbol: str
    base_notional: float
    hedge_notional: float
    base_beta: float
    hedge_beta: float
    net_dollar_exposure: float
    net_beta_exposure: float

    @property
    def neutral(self) -> bool:
        return abs(self.net_dollar_exposure) < 1e-6 and abs(self.net_beta_exposure) < 1e-6


def signed_notional(position: Position) -> float:
    sign = 1.0 if position.side == Side.BUY else -1.0
    return sign * position.notional


def beta_weighted_hedge(base: Position, hedge_symbol: str, base_beta: float, hedge_beta: float) -> HedgePlan:
    base_notional = signed_notional(base)
    hedge_beta = hedge_beta if abs(hedge_beta) > 1e-9 else 1.0
    target_hedge = -(base_notional * base_beta) / hedge_beta
    return HedgePlan(base.symbol, hedge_symbol, base_notional, target_hedge, base_beta, hedge_beta, base_notional + target_hedge, base_notional * base_beta + target_hedge * hedge_beta)


def recalculate(positions: list[Position], betas: dict[str, float], hedge_symbol: str = "BTC/USDT") -> HedgePlan | None:
    if not positions:
        return None
    base = max(positions, key=lambda position: position.notional)
    return beta_weighted_hedge(base, hedge_symbol, betas.get(base.symbol, 1.0), betas.get(hedge_symbol, 1.0))
