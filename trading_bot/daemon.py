"""Long-running read-only market-data and safety monitor.

Execution remains disabled unless an explicitly integrated strategy loop is enabled
on a configured host after sandbox validation.
"""
from __future__ import annotations

import argparse
import time

from trading_bot.config import load_settings
from trading_bot.data import BinancePublicProvider, MarketDataHub
from trading_bot.monitoring import OperationalMonitor
from trading_bot.models import RiskSnapshot
from trading_bot.risk import KillSwitch, RiskEngine
from trading_bot.storage import AuditLog, MarketStore


def run_once(symbols: list[str]) -> dict[str, object]:
    settings = load_settings()
    audit = AuditLog(settings.audit_log)
    store = MarketStore(settings.database)
    provider = BinancePublicProvider()
    hub = MarketDataHub(provider, store, max_age_seconds=settings.max_data_age_seconds, max_latency_ms=settings.max_latency_ms)
    quotes = hub.snapshot(symbols)
    risk = RiskEngine(settings)
    monitor = OperationalMonitor(risk, KillSwitch(settings.state_dir / "kill.json"), audit)
    max_latency = max((quote.latency_ms for quote in quotes), default=0.0)
    snapshot = RiskSnapshot(100_000.0, 100_000.0, 0.0, 4.0, 0.0, 0.0, 0.0, 0.0, 0, 0.0, max_latency, max((quote.spread_bps for quote in quotes), default=0.0))
    result = monitor.check(snapshot)
    store.close()
    return {"quotes": len(quotes), "health": hub.health(), "monitor_ok": result.ok, "reasons": result.reasons}


def main() -> int:
    parser = argparse.ArgumentParser(prog="orca-max-mouny-daemon")
    parser.add_argument("--symbols", default="BTC/USDT")
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    symbols = [value.strip() for value in args.symbols.split(",") if value.strip()]
    if args.once:
        print(run_once(symbols))
        return 0
    while True:
        print(run_once(symbols), flush=True)
        time.sleep(max(args.interval, 1.0))


if __name__ == "__main__":
    raise SystemExit(main())
