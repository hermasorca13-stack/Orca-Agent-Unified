"""Market-neutral arbitrage signal generators."""
from __future__ import annotations

from trading_bot.models import CostEstimate, MarketQuote, PairValidation, Signal, Side


def cross_exchange_signal(buy_quote: MarketQuote, sell_quote: MarketQuote, costs: CostEstimate, *, strategy: str = "cross_exchange_arbitrage") -> Signal | None:
    if buy_quote.symbol != sell_quote.symbol:
        return None
    gross_bps = (sell_quote.bid - buy_quote.ask) / buy_quote.ask * 10_000 if buy_quote.ask else 0.0
    net_bps = gross_bps - costs.total / max(buy_quote.ask, 1e-12) * 10_000
    if net_bps <= 0.0:
        return None
    return Signal(strategy, buy_quote.symbol, Side.BUY, min(net_bps / 100.0, 1.0), net_bps, None, (), 1.0, (f"buy:{buy_quote.exchange}", f"sell:{sell_quote.exchange}", f"net_edge_bps:{net_bps:.3f}"))


def pair_signal(validation: PairValidation, *, entry_z: float = 2.0, exit_z: float = 0.5, strategy: str = "statistical_arbitrage") -> Signal | None:
    if not (validation.cointegrated and validation.stationary):
        return None
    if abs(validation.z_score) < entry_z:
        return None
    side = Side.SELL if validation.z_score > 0 else Side.BUY
    edge = abs(validation.z_score - exit_z) * 10.0
    return Signal(strategy, f"{validation.symbol_a}/{validation.symbol_b}", side, min(abs(validation.z_score) / 4.0, 1.0), edge, None, (), min(abs(validation.z_score) / 4.0, 1.0), ("cointegrated", "stationary", f"z_score:{validation.z_score:.3f}"))
