import json
from pathlib import Path

from trading_bot.analytics.backtest import run_backtest
from trading_bot.analytics.optimizer import optimize_sma, sma_signal
from trading_bot.analytics.crossover_optimizer import crossover_signal, optimize_crossover
from trading_bot.data.providers import BinancePublicProvider
import pandas as pd

provider = BinancePublicProvider(timeout=20.0)
rows = provider.fetch_ohlcv("BTC/USDT", interval="1h", limit=1000)
frame = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
split = int(len(frame) * 0.70)
train = frame.iloc[:split]
test = frame.iloc[split - 220:]
result = optimize_sma(train, fast_values=(5, 10, 15, 20, 30), slow_values=(40, 60, 80, 100, 150), gap_values=(0.0, 5.0, 10.0, 20.0, 30.0, 50.0), min_trades=30)
oos = run_backtest(test, sma_signal(result.parameters))
cross = optimize_crossover(train, fast_values=(5, 10, 15, 20), slow_values=(40, 60, 80, 100, 150), gap_values=(0.0, 5.0, 10.0, 20.0, 30.0, 50.0), min_trades=10)
cross_oos = run_backtest(test, crossover_signal(cross.parameters))
payload = {"sma": {"parameters": result.parameters, "in_sample": result.result.__dict__, "out_of_sample": oos.__dict__, "accepted_for_live": bool(result.accepted and oos.trades >= 30 and result.result.trades + oos.trades >= 200 and oos.net_pnl > 0 and oos.profit_factor > 1.0 and oos.win_rate > 0.50)}, "crossover": {"parameters": cross.parameters, "in_sample": cross.result.__dict__, "out_of_sample": cross_oos.__dict__, "accepted_for_live": bool(cross.accepted and cross_oos.trades >= 30 and cross.result.trades + cross_oos.trades >= 200 and cross_oos.net_pnl > 0 and cross_oos.profit_factor > 1.0 and cross_oos.win_rate > 0.50)}}
Path("docs/optimization_report_2026-08-26.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
print(json.dumps(payload, indent=2, default=str))
