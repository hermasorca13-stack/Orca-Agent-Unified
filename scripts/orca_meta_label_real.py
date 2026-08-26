import json
from pathlib import Path

import pandas as pd

from trading_bot.analytics.optimizer import sma_signal
from trading_bot.analytics.meta_labeling import MetaLabeler, triple_barrier_labels
from trading_bot.data.providers import BinancePublicProvider

provider = BinancePublicProvider(timeout=20.0)
rows = provider.fetch_ohlcv("BTC/USDT", interval="1h", limit=1000)
frame = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
frame = frame.set_index("timestamp")
features, events = triple_barrier_labels(frame, sma_signal({"fast": 15, "slow": 40, "gap_bps": 0.0}), profit_atr=1.5, stop_atr=1.0, horizon=24)
labels = [event.label for event in events]
split = int(len(features) * 0.70)
train_features, test_features = features.iloc[:split], features.iloc[split:]
train_labels, test_labels = labels[:split], labels[split:]
model = MetaLabeler(min_probability=0.55).fit(train_features, train_labels)
probabilities = model.probability(test_features)
accepted = model.accept(test_features)
payload = {"bars": len(frame), "events": len(events), "train_events": len(train_features), "test_events": len(test_features), "test_positive_rate": sum(test_labels) / max(1, len(test_labels)), "meta_accept_rate": float(accepted.mean()) if len(accepted) else 0.0, "meta_mean_probability": float(probabilities.mean()) if len(probabilities) else 0.0}
Path("docs/meta_label_report_2026-08-26.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(json.dumps(payload, indent=2))
