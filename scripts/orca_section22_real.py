"""Section 22 real-data verification; public Binance candles only, no orders or keys."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from trading_bot.analytics.calibration22 import BayesianCalibrator
from trading_bot.analytics.immune_memory22 import ImmuneMemory
from trading_bot.analytics.regime import detect_regime
from trading_bot.analytics.section22 import Section22Layer
from trading_bot.data.providers import BinancePublicProvider
from trading_bot.storage.audit import AuditLog


REPORT_PATH = Path("docs/section22_report_2026-08-26.json")
AUDIT_PATH = Path("/tmp/orca_section22_audit.jsonl")


def main() -> dict:
    rows = BinancePublicProvider(timeout=20.0).fetch_ohlcv("BTC/USDT", interval="1h", limit=1000)
    frame = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
    frame = frame.set_index("timestamp").sort_index()
    returns = frame["close"].pct_change().dropna()
    volatility = returns.rolling(24).std()
    zscore = (returns - returns.rolling(24).mean()) / volatility.replace(0, np.nan)
    regime = detect_regime(frame, funding_rate=0.0)
    audit = AuditLog(AUDIT_PATH)
    calibrator = BayesianCalibrator(seed=22)
    layer = Section22Layer(audit=audit, calibrator=calibrator, immune=ImmuneMemory(radius=0.75, reject_affinity=0.80))
    proposal = layer.propose(context=str(regime.regime.value))
    calibration = None
    if proposal is not None:
        calibration = layer.record_calibration(proposal, score=0.0, cpcv_pass=False, pbo=1.0, dsr=-1.0, shadow_pass=False)
    proxy_observations = 0
    proxy_antigens = 0
    for timestamp in returns.index[24:]:
        ret = float(returns.loc[timestamp])
        vol = float(volatility.loc[timestamp]) if np.isfinite(volatility.loc[timestamp]) else 0.0
        z = float(zscore.loc[timestamp]) if np.isfinite(zscore.loc[timestamp]) else 0.0
        features = (ret, vol, z)
        if ret >= 0:
            layer.immune.add_self(features)
        else:
            observation = layer.on_trade_closed(features=features, pnl=ret, risk_budget=0.005, expected_edge=0.0001, network_stress=False)
            proxy_antigens += int(observation.immune.antigen)
        proxy_observations += 1
    latest_features = (float(returns.iloc[-1]), float(volatility.iloc[-1]), float(zscore.iloc[-1]) if np.isfinite(zscore.iloc[-1]) else 0.0)
    latest_screen = layer.screen_signal(latest_features)
    detector_values = list(layer.immune.detectors.values())
    payload = {
        "data_source": "Binance public REST OHLCV",
        "symbol": "BTC/USDT",
        "interval": "1h",
        "bars": len(frame),
        "first_timestamp": frame.index[0].isoformat(),
        "last_timestamp": frame.index[-1].isoformat(),
        "market_regime_context": str(regime.regime.value),
        "calibration": {"proposal_created": proposal is not None, "proposal": proposal.__dict__ if proposal else None, "result": calibration.__dict__ if calibration else None, "execution_eligible": False},
        "immune_proxy_exercise": {"observations": proxy_observations, "proxy_antigens": proxy_antigens, "detector_metrics": layer.immune.metrics(), "confirmed_hits": sum(detector.confirmed_hits for detector in detector_values), "false_positives": sum(detector.false_positives for detector in detector_values), "latest_screen": latest_screen.__dict__},
        "audit": {"path": str(AUDIT_PATH), "events": len(AUDIT_PATH.read_text(encoding="utf-8").splitlines()) if AUDIT_PATH.exists() else 0},
        "comparison": {"manual_quarterly_vs_calibrated_performance": "not_performed; no matched strategy backtest was run in this diagnostic"},
        "execution": {"orders_submitted": 0, "live_authority": False, "keys_used": False},
        "disclosure": "Real public market data was used. Immune labels are a proxy exercise over candle-return feature vectors, not verified trade outcomes; no performance improvement or Live readiness is claimed.",
    }
    REPORT_PATH.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))
    return payload


if __name__ == "__main__":
    main()
