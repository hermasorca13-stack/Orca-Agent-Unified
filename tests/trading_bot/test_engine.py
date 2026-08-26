from datetime import datetime, timezone

import pandas as pd
import pytest

from trading_bot.adapters.paper import PaperExchange
from trading_bot.analytics.statistics import validate_pair
from trading_bot.strategies.arbitrage import cross_exchange_signal
from trading_bot.config.settings import ConfigurationError, ExchangeCredentials, Settings
from trading_bot.execution.engine import ExecutionEngine, ExecutionPlan
from trading_bot.models import CostEstimate, MarketQuote, RiskSnapshot, Side
from trading_bot.risk.gates import MarketContext, RiskEngine
from trading_bot.storage.audit import AuditLog
from trading_bot.strategies.technical import technical_signal


def test_withdrawal_permission_is_rejected():
    settings = Settings(credentials=(ExchangeCredentials("binance", "k", "s", enable_withdraw=True),))
    with pytest.raises(ConfigurationError):
        settings.validate_startup()


def test_paper_execution_is_staged(tmp_path):
    exchange = PaperExchange(starting_cash=100_000)
    exchange.set_quote(MarketQuote("paper", "BTC/USDT", 100.0, 101.0))
    audit = AuditLog(tmp_path / "audit.jsonl")
    fills = ExecutionEngine({"paper": exchange}, audit).staged_entry(ExecutionPlan("paper", "BTC/USDT", Side.BUY, 10.0, 101.0, slices=4))
    assert len(fills) == 4
    assert sum(fill.amount for fill in fills) == pytest.approx(10.0)
    assert (tmp_path / "audit.jsonl").read_text().count("order_fill") == 4


def test_risk_gate_fails_closed_on_stale_data(tmp_path):
    settings = Settings(audit_log=tmp_path / "audit.jsonl", database=tmp_path / "db.sqlite3")
    engine = RiskEngine(settings)
    snapshot = RiskSnapshot(100_000, 100_000, 0, 4, 0, 0, 0, 0, 0, 4.0, 10.0, 1.0)
    from trading_bot.models import Signal
    signal = Signal("x", "BTC/USDT", Side.BUY, 1, 20, None, (), 1, ("a", "b", "c"))
    result = engine.trade_gate(signal, MarketContext(), snapshot, CostEstimate(4, 1, 1, 0, 0, 0, 0))
    assert not result.allowed
    assert "data_age_exceeded" in result.reasons


def test_audit_redacts_secret_fields(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    audit.write("credentials", {"api_key": "secret", "api_secret": "private", "safe": "value"})
    text = (tmp_path / "audit.jsonl").read_text()
    assert '"secret"' not in text and '"private"' not in text
    assert "value" in text


def test_cross_exchange_signal_is_net_positive():
    buy = MarketQuote("a", "BTC/USDT", 99.0, 100.0)
    sell = MarketQuote("b", "BTC/USDT", 101.0, 102.0)
    signal = cross_exchange_signal(buy, sell, CostEstimate(0.1, 0.1, 0.1, 0, 0, 0, 0))
    assert signal is not None
    assert signal.expected_edge_bps > 0


def test_technical_signal_requires_three_confirmations():
    index = pd.date_range("2025-01-01", periods=260, freq="D", tz="UTC")
    close = pd.Series([100 + i * 0.2 + ((i % 7) - 3) * 0.35 for i in range(260)], index=index)
    frame = pd.DataFrame({"open": close - 0.1, "high": close + 0.5, "low": close - 0.5, "close": close, "volume": 2_000_000.0}, index=index)
    signal = technical_signal(frame, "BTC/USDT")
    assert signal is not None
    assert len(signal.reasons) >= 3
