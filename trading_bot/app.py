"""ORCA Max Mouny application service."""
from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone

import pandas as pd

from trading_bot.adapters import PaperExchange
from trading_bot.analytics.execution_quality23 import VenueQuote, vpin
from trading_bot.analytics.section20 import Section20Layer
from trading_bot.data.providers import BinancePublicProvider
from trading_bot.config import ConfigurationError, load_settings
from trading_bot.execution.engine import ExecutionEngine, ExecutionPlan
from trading_bot.models import CostEstimate, MarketQuote, RiskSnapshot, Side, TradingMode
from trading_bot.risk.gates import MarketContext, RiskEngine
from trading_bot.risk.kill_switch import KillSwitch
from trading_bot.storage.audit import AuditLog
from trading_bot.strategies.technical import technical_signal


def _adaptive_paper_gate(layer: Section20Layer, audit: AuditLog, signal, quote: MarketQuote, amount: float):
    context = layer.section24_context(now=quote.timestamp, currency="USD")
    audit.write("section24_context", context)
    toxicity = vpin([quote.mid] * 10, [1.0] * 10)
    decision = layer.section23_execution(
        prior_gates_allowed=True,
        toxicity=toxicity,
        venues=[VenueQuote("paper", max(amount * quote.mid, 1.0), 4.0, 1.0, quote.latency_ms)],
        required_notional=max(amount * quote.mid, 1.0),
        paper_mode=True,
    )
    audit.write("section23_runtime_decision", decision)
    return decision


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
    kill_switch = KillSwitch(settings.state_dir / "kill.json")
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
        if gate.code == "EMERGENCY_STOP":
            kill_switch.trigger("risk_gate:" + ";".join(gate.reasons), close_positions=True)
        print(f"REJECTED {gate.code}: {','.join(gate.reasons)}")
        return 0
    amount = risk.position_size(snapshot.equity, abs(quote.mid - (signal.stop_price or quote.mid)), quote.mid, context.atr_pct)
    adaptive = _adaptive_paper_gate(Section20Layer(audit=audit, kill_switch=kill_switch), audit, signal, quote, amount)
    if not adaptive.allowed_after_prior_gates or adaptive.order_fraction <= 0.0:
        print(f"REJECTED {adaptive.reason}")
        return 0
    fills = execution.staged_entry(ExecutionPlan("paper", signal.symbol, signal.side, amount * adaptive.order_fraction, quote.ask, strategy=signal.strategy, approved=True))
    print(f"EXECUTED_PAPER fills={len(fills)} amount={sum(fill.amount for fill in fills):.8f}")
    return 0


def paper_history_demo() -> int:
    settings = load_settings()
    if settings.mode != TradingMode.PAPER:
        raise ConfigurationError("paper-history requires ORCA_TRADING_MODE=paper")
    provider = BinancePublicProvider(timeout=20.0)
    rows = provider.fetch_ohlcv("BTC/USDT", interval="1h", limit=260)
    frame = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
    frame = frame.set_index("timestamp")
    signal = technical_signal(frame, "BTC/USDT")
    audit = AuditLog(settings.audit_log)
    kill_switch = KillSwitch(settings.state_dir / "kill.json")
    if signal is None:
        audit.write("signal_rejected", {"reason": "no_three_factor_signal", "source": "Binance historical OHLCV"})
        print({"mode": "paper", "action": "NO_SIGNAL", "bars": len(frame), "source": "Binance historical OHLCV"})
        return 0
    last = float(frame["close"].iloc[-1])
    spread = last * 0.0001
    quote = MarketQuote("paper", signal.symbol, last - spread / 2, last + spread / 2, bid_size=10.0, ask_size=10.0, volume_24h=float(frame["volume"].tail(24).sum()), latency_ms=0.0)
    exchange = PaperExchange()
    exchange.set_quote(quote)
    risk = RiskEngine(settings)
    snapshot = RiskSnapshot(100_000.0, 100_000.0, 0.0, 4.0, 0.0, 0.0, 0.0, 0.0, 0, 0.0, 0.0, quote.spread_bps)
    costs = CostEstimate(4.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0)
    gate = risk.trade_gate(signal, MarketContext(), snapshot, costs)
    audit.write("risk_gate", gate)
    if not gate.allowed:
        if gate.code == "EMERGENCY_STOP":
            kill_switch.trigger("risk_gate:" + ";".join(gate.reasons), close_positions=True)
        print({"mode": "paper", "action": "REJECTED", "code": gate.code, "reasons": gate.reasons})
        return 0
    amount = risk.position_size(snapshot.equity, max(abs(quote.mid - (signal.stop_price or quote.mid)), quote.mid * 0.005), quote.mid, 0.01)
    adaptive = _adaptive_paper_gate(Section20Layer(audit=audit, kill_switch=kill_switch), audit, signal, quote, amount)
    if not adaptive.allowed_after_prior_gates or adaptive.order_fraction <= 0.0:
        print({"mode": "paper", "action": "REJECTED", "code": adaptive.reason})
        return 0
    fills = ExecutionEngine({"paper": exchange}, audit).staged_entry(ExecutionPlan("paper", signal.symbol, signal.side, amount * adaptive.order_fraction, quote.ask if signal.side == Side.BUY else quote.bid, strategy=signal.strategy, approved=True))
    print({"mode": "paper", "action": "EXECUTED_PAPER", "fills": len(fills), "amount": sum(fill.amount for fill in fills), "bars": len(frame), "source": "Binance historical OHLCV"})
    return 0


def paper_live_demo() -> int:
    settings = load_settings()
    if settings.mode != TradingMode.PAPER:
        raise ConfigurationError("paper-live requires ORCA_TRADING_MODE=paper")
    provider = BinancePublicProvider(timeout=20.0)
    rows = provider.fetch_ohlcv("BTC/USDT", interval="1h", limit=260)
    frame = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
    frame = frame.set_index("timestamp")
    signal = technical_signal(frame, "BTC/USDT")
    quote = provider.fetch_quote("BTC/USDT")
    audit = AuditLog(settings.audit_log)
    kill_switch = KillSwitch(settings.state_dir / "kill.json")
    audit.write("paper_live_snapshot", {"quote": quote, "bars": len(frame)})
    if signal is None:
        audit.write("signal_rejected", {"reason": "no_three_factor_signal", "symbol": quote.symbol})
        print({"mode": "paper", "action": "NO_SIGNAL", "symbol": quote.symbol, "mid": quote.mid})
        return 0
    exchange = PaperExchange()
    exchange.set_quote(MarketQuote("paper", quote.symbol, quote.bid, quote.ask, bid_size=quote.bid_size, ask_size=quote.ask_size, volume_24h=quote.volume_24h, timestamp=quote.timestamp, latency_ms=quote.latency_ms))
    risk = RiskEngine(settings)
    snapshot = RiskSnapshot(100_000.0, 100_000.0, 0.0, 4.0, 0.0, 0.0, 0.0, 0.0, 0, 0.0, quote.latency_ms, quote.spread_bps)
    costs = CostEstimate(4.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0)
    gate = risk.trade_gate(signal, MarketContext(), snapshot, costs)
    audit.write("risk_gate", gate)
    if not gate.allowed:
        if gate.code == "EMERGENCY_STOP":
            kill_switch.trigger("risk_gate:" + ";".join(gate.reasons), close_positions=True)
        print({"mode": "paper", "action": "REJECTED", "code": gate.code, "reasons": gate.reasons})
        return 0
    amount = risk.position_size(snapshot.equity, abs(quote.mid - (signal.stop_price or quote.mid)), quote.mid, 0.01)
    adaptive = _adaptive_paper_gate(Section20Layer(audit=audit, kill_switch=kill_switch), audit, signal, quote, amount)
    if not adaptive.allowed_after_prior_gates or adaptive.order_fraction <= 0.0:
        print({"mode": "paper", "action": "REJECTED", "code": adaptive.reason})
        return 0
    fills = ExecutionEngine({"paper": exchange}, audit).staged_entry(ExecutionPlan("paper", signal.symbol, signal.side, amount * adaptive.order_fraction, quote.ask if signal.side == Side.BUY else quote.bid, strategy=signal.strategy, approved=True))
    print({"mode": "paper", "action": "EXECUTED_PAPER", "fills": len(fills), "amount": sum(fill.amount for fill in fills), "source": "Binance public data"})
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="orca-max-mouny")
    parser.add_argument("command", choices=("paper-demo", "paper-history", "paper-live", "status"))
    args = parser.parse_args(argv)
    if args.command == "paper-demo":
        return paper_demo()
    if args.command == "paper-history":
        return paper_history_demo()
    if args.command == "paper-live":
        return paper_live_demo()
    settings = load_settings()
    print({"name": settings.name, "mode": settings.mode.value, "active_exchanges": settings.active_exchanges, "state_dir": str(settings.state_dir)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
