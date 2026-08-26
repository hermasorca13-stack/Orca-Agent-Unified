"""ORCA Max Mouny application service."""
from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone

import pandas as pd

from trading_bot.adapters import PaperExchange
from trading_bot.config import ConfigurationError, load_settings
from trading_bot.execution.engine import ExecutionEngine, ExecutionPlan
from trading_bot.models import CostEstimate, MarketQuote, RiskSnapshot, Side, TradingMode
from trading_bot.risk.gates import MarketContext, RiskEngine
from trading_bot.storage.audit import AuditLog
from trading_bot.strategies.technical import technical_signal


def build_adapters(settings):
    paper = PaperExchange()
    if settings.mode == TradingMode.PAPER:
        return {"paper": paper}
    from trading_bot.adapters.ccxt_adapter import CcxtExchange
    adapters = {}
    for credential in settings.credentials:
        if credential.name in settings.active_exchanges and credential.configured:
            adapters[credential.name] = CcxtExchange(
                credential.name,
                credential.api_key,
                credential.api_secret,
                password=credential.password,
                uid=credential.uid,
                sandbox=settings.mode == TradingMode.SANDBOX or credential.sandbox,
            )
    if not adapters:
        raise ConfigurationError("no configured exchange adapter for selected mode")
    return adapters


def paper_demo() -> int:
    settings = load_settings()
    if settings.mode != TradingMode.PAPER:
        raise ConfigurationError("paper-demo requires ORCA_TRADING_MODE=paper")
    exchange = PaperExchange()
    audit = AuditLog(settings.audit_log)
    risk = RiskEngine(settings)
    execution = ExecutionEngine({"paper": exchange}, audit)
    index = pd.date_range(end=datetime.now(timezone.utc), periods=260, freq="h")
    close = pd.Series([100 + i * 0.15 + ((i % 17) - 8) * 0.35 for i in range(len(index))], index=index)
    frame = pd.DataFrame({"open": close.shift(1).fillna(close), "high": close + 0.4, "low": close - 0.4, "close": close, "volume": 2_000_000.0}, index=index)
    signal = technical_signal(frame, "BTC/USDT")
    if signal is None:
        audit.write("signal_rejected", {"reason": "no_three_factor_signal"})
        print("NO_SIGNAL")
        return 0
    quote = MarketQuote("paper", signal.symbol, float(close.iloc[-1] - 0.1), float(close.iloc[-1] + 0.1), volume_24h=1_000_000_000.0)
    exchange.set_quote(quote)
    snapshot = RiskSnapshot(100_000.0, 100_000.0, 0.0, 4.0, 0.0, 0.0, 0.0, 0.0, 0, 0.0, 0.0, quote.spread_bps)
    context = MarketContext()
    costs = CostEstimate(4.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0)
    gate = risk.trade_gate(signal, context, snapshot, costs)
    audit.write("risk_gate", gate)
    if not gate.allowed:
        print(f"REJECTED {gate.code}: {','.join(gate.reasons)}")
        return 0
    amount = risk.position_size(snapshot.equity, abs(quote.mid - (signal.stop_price or quote.mid)), quote.mid, context.atr_pct)
    fills = execution.staged_entry(ExecutionPlan("paper", signal.symbol, signal.side, amount, quote.ask, strategy=signal.strategy))
    print(f"EXECUTED_PAPER fills={len(fills)} amount={sum(fill.amount for fill in fills):.8f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="orca-max-mouny")
    parser.add_argument("command", choices=("paper-demo", "status"))
    args = parser.parse_args(argv)
    if args.command == "paper-demo":
        return paper_demo()
    settings = load_settings()
    print({"name": settings.name, "mode": settings.mode.value, "active_exchanges": settings.active_exchanges, "state_dir": str(settings.state_dir)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
