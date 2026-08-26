"""Real-data Section 21 verification; public Binance data only, never submits orders."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from trading_bot.analytics.alpha_discovery import evolve
from trading_bot.analytics.causal import validate_causality
from trading_bot.analytics.contagion import ContagionGraph
from trading_bot.analytics.explainability import drift_report
from trading_bot.analytics.governance21 import Section21Governance
from trading_bot.analytics.stress_generator import StressGenerator
from trading_bot.analytics.tail_risk import report as tail_risk_report
from trading_bot.data.providers import BinancePublicProvider


REPORT_PATH = Path("docs/section21_report_2026-08-26.json")


def main() -> dict:
    rows = BinancePublicProvider(timeout=20.0).fetch_ohlcv("BTC/USDT", interval="1h", limit=1000)
    frame = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
    frame = frame.set_index("timestamp").sort_index()
    returns = frame["close"].pct_change().dropna()
    split = int(len(frame) * 0.70)
    candidates = evolve(frame.assign(return_1=returns.reindex(frame.index).fillna(0.0), return_5=frame["close"].pct_change(5).fillna(0.0), volatility=returns.rolling(24).std().fillna(0.0), funding_rate=0.0, spread_bps=1.0), generations=2, population_size=8)
    causal = validate_causality(frame["close"].pct_change().fillna(0.0), frame["close"].pct_change(2).fillna(0.0), source_name="btc_return_1h", target_name="btc_return_2h", economic_mechanism="lagged_return_dependence_is_diagnostic_only")
    tail = tail_risk_report(returns.to_numpy())
    stress = StressGenerator(seed=21, block_size=8).generate(returns.tolist(), scenarios=24, length=min(returns.size, 240))
    worst = max(stress, key=lambda item: item.max_drawdown)
    contagion = ContagionGraph().assess({"binance_public": (-returns.rolling(24).mean().fillna(0.0) / returns.rolling(24).std().replace(0, np.nan)).fillna(0.0).tolist()})
    drift = drift_report(returns.iloc[:split].to_numpy(), returns.iloc[split:].to_numpy(), "btc_return_1h")
    governance = Section21Governance().evaluate(causal_pass=causal.accepted, cpcv_pass=False, pbo=1.0, dsr=-1.0, shadow_pass=False, tail_pass=tail.accepted, drift_warning=drift.warning)
    payload = {
        "data_source": "Binance public REST OHLCV",
        "symbol": "BTC/USDT",
        "interval": "1h",
        "bars": len(frame),
        "first_timestamp": frame.index[0].isoformat(),
        "last_timestamp": frame.index[-1].isoformat(),
        "returns": len(returns),
        "alpha_candidates": len(candidates),
        "alpha_execution_eligible": sum(candidate.execution_eligible for candidate in candidates),
        "causal": causal.__dict__,
        "tail_risk": tail.__dict__,
        "stress": {"scenarios": len(stress), "worst_case_max_drawdown": worst.max_drawdown, "all_stop_tightening_only": all(item.stop_tightening_required for item in stress)},
        "contagion": {"affected": contagion.affected, "exposure_multiplier": contagion.exposure_multiplier, "action": contagion.action},
        "drift": drift.__dict__,
        "governance": governance.__dict__,
        "execution": {"orders_submitted": 0, "live_authority": False, "keys_used": False},
        "disclosure": "Diagnostic verification only. No performance improvement, profitability, or Live readiness is claimed. Section 21 cannot authorize Live execution.",
    }
    REPORT_PATH.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))
    return payload


if __name__ == "__main__":
    main()
