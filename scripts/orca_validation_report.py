"""Generate a real-data validation report without placing orders."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from trading_bot.analytics.validation import monte_carlo_max_drawdown, out_of_sample, stress_suite, walk_forward
from trading_bot.data.providers import BinancePublicProvider


def main() -> int:
    provider = BinancePublicProvider(timeout=20.0)
    rows = provider.fetch_ohlcv("BTC/USDT", interval="1h", limit=1000)
    frame = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
    frame = frame.set_index("timestamp")

    def signal(history: pd.DataFrame) -> float | None:
        if len(history) < 20:
            return None
        fast = history["close"].rolling(10).mean().iloc[-1]
        slow = history["close"].rolling(20).mean().iloc[-1]
        return 1.0 if fast > slow else -1.0

    in_sample, out_sample = out_of_sample(frame, signal)
    wf = walk_forward(frame, signal, train_size=220, test_size=60)
    returns = [value.net_pnl / 100_000.0 for value in wf if value.trades]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "Binance public REST /api/v3/klines",
        "symbol": "BTC/USDT",
        "interval": "1h",
        "bars": len(frame),
        "range": [frame.index[0].isoformat(), frame.index[-1].isoformat()],
        "in_sample": in_sample.__dict__,
        "out_of_sample": out_sample.__dict__,
        "walk_forward_windows": len(wf),
        "monte_carlo_p95_max_drawdown": monte_carlo_max_drawdown(returns) if returns else None,
        "stress": stress_suite(frame, signal),
        "acceptance_gate": {"sharpe_gt_2": out_sample.sharpe > 2.0, "profit_factor_gt_2": out_sample.profit_factor > 2.0, "max_drawdown_lt_20pct": out_sample.max_drawdown < 0.20, "win_rate_gt_50pct": out_sample.win_rate > 0.50},
    }
    output = Path("data/orca_max_mouny/validation_report.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
