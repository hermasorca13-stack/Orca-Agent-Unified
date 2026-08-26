"""Read-only cross-source smoke check for Section 23."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from trading_bot.analytics.data_quality23 import DataQualityGate, SourcePriority
from trading_bot.analytics.public_sources23 import PublicSourceError, fetch_coinbase_ticker, fetch_kraken_ticker
from trading_bot.data.providers import BinancePublicProvider

REPORT = Path("docs/cross_source_report_2026-08-26.json")


def main() -> dict:
    provider = BinancePublicProvider(timeout=20.0)
    results: dict[str, object] = {"as_of": datetime.now(timezone.utc).isoformat(), "data_source": "public REST read-only", "orders_submitted": 0, "keys_used": False}
    values: dict[str, float] = {}
    try:
        quote = provider.fetch_quote("BTC/USDT")
        values["binance"] = (quote.bid + quote.ask) / 2.0
        results["binance"] = quote.__dict__
    except Exception as exc:
        results["binance_error"] = type(exc).__name__
    for name, loader in (("coinbase", fetch_coinbase_ticker), ("kraken", fetch_kraken_ticker)):
        try:
            ticker = loader()
            values[name] = (ticker.bid + ticker.ask) / 2.0
            results[name] = ticker.__dict__
        except (PublicSourceError, Exception) as exc:
            results[f"{name}_error"] = type(exc).__name__
    quality = DataQualityGate(deviation_limit=0.01, priorities=(SourcePriority("spot", ("binance", "coinbase", "kraken")),)).compare("spot", values)
    results["source_values"] = values
    results["quality"] = quality.__dict__
    latencies = [float(item["latency_ms"]) for key, item in results.items() if key in {"binance", "coinbase", "kraken"} and isinstance(item, dict) and "latency_ms" in item]
    latency_ok = bool(latencies) and max(latencies) <= 500.0
    results["latency_gate"] = {"max_latency_ms": max(latencies) if latencies else None, "limit_ms": 500.0, "ok": latency_ok}
    results["signal_allowed"] = bool(quality.accepted and len(values) >= 2 and latency_ok)
    results["disclosure"] = "Public read-only diagnostics; prices are asynchronous cross-source observations and are not a trading signal."
    REPORT.write_text(json.dumps(results, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2, default=str))
    return results


if __name__ == "__main__":
    main()
