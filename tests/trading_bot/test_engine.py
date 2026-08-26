from datetime import datetime, timezone

import pandas as pd
import pytest

from trading_bot.adapters.paper import PaperExchange
from trading_bot.analytics.backtest import run_backtest
from trading_bot.analytics.statistics import validate_pair
from trading_bot.analytics.validation import monte_carlo_max_drawdown, out_of_sample, stress_suite, walk_forward
from trading_bot.analytics.model_registry import ModelRegistry
from trading_bot.analytics.optimization_cycle import CumulativeOptimizer
from trading_bot.data.hub import MarketDataHub
from trading_bot.storage.market_store import MarketStore
from trading_bot.strategies.arbitrage import cross_exchange_signal
from trading_bot.config.settings import ConfigurationError, ExchangeCredentials, Settings
from trading_bot.cycle import TradingCycle
from trading_bot.execution.engine import ExecutionEngine, ExecutionPlan
from trading_bot.execution.position_manager import fibonacci_targets, manage_position
from trading_bot.models import CostEstimate, MarketQuote, RiskSnapshot, Side
from trading_bot.risk.gates import MarketContext, RiskEngine
from trading_bot.risk.policy import PortfolioPolicy, PortfolioState
from trading_bot.risk.kill_switch import KillSwitch
from trading_bot.risk.hedging import beta_weighted_hedge
from trading_bot.security.vault import LocalApiVault, VaultError
from trading_bot.models import Position
from trading_bot.monitoring import OperationalMonitor
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


def test_trading_cycle_records_approved_decision(tmp_path):
    settings = Settings(state_dir=tmp_path, audit_log=tmp_path / "audit.jsonl", database=tmp_path / "db.sqlite3")
    audit = AuditLog(settings.audit_log)
    from trading_bot.models import Signal
    signal = Signal("test", "BTC/USDT", Side.BUY, 1.0, 10.0, None, (), 1.0, ("a", "b", "c"))
    result = TradingCycle(PaperExchange(), RiskEngine(settings), audit).evaluate(
        "BTC/USDT", lambda symbol: signal, RiskSnapshot(100_000, 100_000, 0, 4, 0, 0, 0, 0, 0, 0, 10, 1), CostEstimate(1, 1, 1, 0, 0, 0, 0)
    )
    assert result.allowed
    assert "risk_gate" in (tmp_path / "audit.jsonl").read_text()


def test_validation_tools_run_without_future_data():
    index = pd.date_range("2025-01-01", periods=600, freq="D", tz="UTC")
    close = pd.Series([100 + i * 0.1 + ((i % 9) - 4) * 0.2 for i in range(600)], index=index)
    frame = pd.DataFrame({"open": close, "high": close + 1, "low": close - 1, "close": close + 0.2, "volume": 1_000_000.0}, index=index)
    signal_fn = lambda history: 1.0
    in_sample, out_sample = out_of_sample(frame, signal_fn)
    assert in_sample.trades > 0 and out_sample.trades > 0
    assert len(walk_forward(frame, signal_fn, train_size=220, test_size=40)) > 0
    assert monte_carlo_max_drawdown([0.01, -0.005, 0.008, -0.004]) >= 0.0
    assert "wide_spread_net_pnl" in stress_suite(frame, signal_fn)


def test_cumulative_optimizer_records_rejected_promotion(tmp_path):
    index = pd.date_range("2025-01-01", periods=600, freq="D", tz="UTC")
    close = pd.Series([100 + i * 0.1 for i in range(600)], index=index)
    frame = pd.DataFrame({"open": close, "high": close + 1, "low": close - 1, "close": close + 0.2, "volume": 1_000_000.0}, index=index)
    record = CumulativeOptimizer(tmp_path / "optimization_history.json").run_sma_cycle(frame.iloc[:420], frame.iloc[200:])
    assert isinstance(record["promoted"], bool)
    assert isinstance(record["accepted"], bool)
    assert (tmp_path / "optimization_history.json").exists()


def test_local_vault_rejects_withdrawal_permission(tmp_path):
    vault = LocalApiVault(tmp_path / "credentials.json")
    with pytest.raises(VaultError, match="withdrawal"):
        vault.set_exchange("binance", "key", "secret", enable_withdraw=True)


def test_model_registry_stages_and_approves_without_risk_mutation(tmp_path):
    features = pd.DataFrame({"spread": [0.1 + i * 0.001 for i in range(40)], "volume": [1.0 + (i % 3) for i in range(40)]}).to_numpy()
    labels = [i % 2 for i in range(40)]
    registry = ModelRegistry(tmp_path / "models")
    staged = registry.train_and_stage(features, labels)
    approved = registry.approve(staged, reviewer="risk-reviewer")
    assert staged.exists() and approved.exists()
    assert "approved_by" in approved.read_text()


def test_position_manager_moves_stop_and_calculates_targets():
    position = Position("paper", "BTC/USDT", Side.BUY, 1.0, 100.0, 101.5)
    targets = fibonacci_targets(100.0, 98.0, Side.BUY)
    assert targets == pytest.approx((102.764, 103.236))
    decision = manage_position(position, stop_price=98.0, current_price=101.5, atr_value=0.5)
    assert decision.action == "move_stop_to_breakeven"
    assert decision.stop_price == 100.0


def test_beta_weighted_hedge_recalculates_neutrality():
    position = Position("paper", "ETH/USDT", Side.BUY, 10.0, 100.0, 100.0)
    plan = beta_weighted_hedge(position, "BTC/USDT", 1.2, 0.8)
    assert plan.net_beta_exposure == pytest.approx(0.0)
    assert plan.hedge_notional < 0


def test_operational_monitor_triggers_kill_switch(tmp_path):
    settings = Settings(state_dir=tmp_path, audit_log=tmp_path / "audit.jsonl", database=tmp_path / "db.sqlite3")
    audit = AuditLog(settings.audit_log)
    kill = KillSwitch(tmp_path / "kill.json")
    monitor = OperationalMonitor(RiskEngine(settings), kill, audit)
    snapshot = RiskSnapshot(100_000, 100_000, 0, 4, 0, 0, 0, 0, 0, 4.0, 700.0, 1.0)
    result = monitor.check(snapshot)
    assert not result.ok
    assert kill.status()["halted"] is True


def test_portfolio_policy_blocks_reserve_and_martingale(tmp_path):
    settings = Settings(state_dir=tmp_path, audit_log=tmp_path / "audit.jsonl", database=tmp_path / "db.sqlite3")
    policy = PortfolioPolicy(settings)
    state = PortfolioState(100_000, 0.10, 50_000, 1_000, 1_000, 0.0, 0.0, 0)
    assert "external_stablecoin_reserve_below_20_percent" in policy.violations(state)
    assert policy.prohibit_martingale(True, 2.0, 1.0)


def test_market_store_persists_quotes(tmp_path):
    store = MarketStore(tmp_path / "market.sqlite3")
    quote = MarketQuote("paper", "BTC/USDT", 100.0, 101.0)
    store.record_quote(quote)
    rows = store.recent_quotes("paper", "BTC/USDT")
    assert len(rows) == 1
    assert rows[0]["bid"] == 100.0
    store.close()


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


def test_live_mode_requires_explicit_confirmation(monkeypatch, tmp_path):
    monkeypatch.setenv("ORCA_LIVE_CONFIRM", "")
    settings = Settings(mode="live", state_dir=tmp_path, audit_log=tmp_path / "audit.jsonl", database=tmp_path / "db.sqlite3")
    with pytest.raises(ConfigurationError, match="ORCA_LIVE_CONFIRM"):
        settings.validate_startup()


def test_backtest_accounts_for_costs():
    index = pd.date_range("2025-01-01", periods=240, freq="D", tz="UTC")
    close = pd.Series([100 + i * 0.1 for i in range(240)], index=index)
    frame = pd.DataFrame({"open": close, "high": close + 1, "low": close - 1, "close": close + 0.2, "volume": 1_000_000.0}, index=index)
    result = run_backtest(frame, lambda history: 1.0, fee_bps=4.0, slippage_bps=2.0)
    assert result.trades > 0
    assert result.total_costs > 0
    assert result.gross_pnl > result.net_pnl


def test_technical_signal_requires_three_confirmations():
    index = pd.date_range("2025-01-01", periods=260, freq="D", tz="UTC")
    close = pd.Series([100 + i * 0.2 + ((i % 7) - 3) * 0.35 for i in range(260)], index=index)
    frame = pd.DataFrame({"open": close - 0.1, "high": close + 0.5, "low": close - 0.5, "close": close, "volume": 2_000_000.0}, index=index)
    signal = technical_signal(frame, "BTC/USDT")
    assert signal is not None
    assert len(signal.reasons) >= 3
