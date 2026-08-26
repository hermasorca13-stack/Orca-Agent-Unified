"""Strategy registry and deterministic signal helpers."""
from __future__ import annotations

from dataclasses import dataclass

from trading_bot.models import CostEstimate, MarketQuote, Signal, Side
from trading_bot.strategies.arbitrage import cross_exchange_signal
from trading_bot.strategies.technical import technical_signal


@dataclass(frozen=True)
class StrategySpec:
    name: str
    enabled: bool = True
    market_neutral: bool = True


def basis_signal(spot: MarketQuote, future: MarketQuote, costs: CostEstimate, *, min_edge_bps: float = 20.0) -> Signal | None:
    basis_bps = (future.bid - spot.ask) / spot.ask * 10_000 if spot.ask else 0.0
    net = basis_bps - costs.total / max(spot.ask, 1e-12) * 10_000
    if net < min_edge_bps:
        return None
    return Signal("cash_and_carry_basis", spot.symbol, Side.BUY, 1.0, net, None, (), 1.0, ("buy_spot", "sell_future", f"net_basis_bps:{net:.3f}"))


def funding_signal(long_quote: MarketQuote, short_quote: MarketQuote, costs: CostEstimate, *, min_edge_bps: float = 10.0) -> Signal | None:
    edge_bps = (short_quote.funding_rate - long_quote.funding_rate) * 10_000 - costs.total / max(long_quote.mid, 1e-12) * 10_000
    if edge_bps < min_edge_bps:
        return None
    return Signal("funding_rate_arbitrage", long_quote.symbol, Side.BUY, 1.0, edge_bps, None, (), 1.0, ("funding_spread", f"net_funding_bps:{edge_bps:.3f}"))


def calendar_spread_signal(near: MarketQuote, dated: MarketQuote, costs: CostEstimate, *, min_edge_bps: float = 15.0) -> Signal | None:
    edge_bps = (dated.bid - near.ask) / near.ask * 10_000 - costs.total / max(near.ask, 1e-12) * 10_000
    if edge_bps < min_edge_bps:
        return None
    return Signal("calendar_spread", near.symbol, Side.BUY, 1.0, edge_bps, None, (), 1.0, ("near_leg", "dated_leg"))


def market_making_signal(quote: MarketQuote, inventory: float, *, inventory_limit: float = 1.0) -> Signal | None:
    if abs(inventory) >= inventory_limit or quote.spread_bps <= 2.0:
        return None
    side = Side.SELL if inventory > 0 else Side.BUY
    return Signal("market_making", quote.symbol, side, 0.5, quote.spread_bps, None, (), 0.6, ("inventory_neutralization", f"spread_bps:{quote.spread_bps:.3f}"))


def volatility_signal(symbol: str, implied_vol: float, realized_vol: float, costs: CostEstimate) -> Signal | None:
    edge_bps = (implied_vol - realized_vol) * 10_000 - costs.total
    if edge_bps <= 0:
        return None
    side = Side.SELL if implied_vol > realized_vol else Side.BUY
    return Signal("volatility_arbitrage", symbol, side, 0.7, edge_bps, None, (), 0.7, ("implied_vs_realized_vol",))


STRATEGIES = (
    StrategySpec("cross_exchange_arbitrage"),
    StrategySpec("cash_and_carry_basis"),
    StrategySpec("funding_rate_arbitrage"),
    StrategySpec("calendar_spread"),
    StrategySpec("statistical_arbitrage"),
    StrategySpec("market_making"),
    StrategySpec("volatility_arbitrage"),
    StrategySpec("momentum", market_neutral=False),
)

__all__ = ["STRATEGIES", "StrategySpec", "basis_signal", "funding_signal", "calendar_spread_signal", "market_making_signal", "volatility_signal", "technical_signal", "cross_exchange_signal"]
