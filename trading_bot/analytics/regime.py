"""Market regime detection and adaptive entry controls."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd


class Regime(str, Enum):
    QUIET = "quiet"
    TRANSITIONAL = "transitional"
    TURBULENT = "turbulent"


@dataclass(frozen=True)
class RegimeSnapshot:
    regime: Regime
    realized_vol: float
    volume_z: float
    funding_abs: float
    min_confirmations: int
    z_entry_abs: float
    strategy_weights: dict[str, float]


def detect_regime(frame: pd.DataFrame, funding_rate: float = 0.0, *, window: int = 30) -> RegimeSnapshot:
    returns = frame["close"].pct_change().dropna()
    realized_vol = float(returns.tail(window).std(ddof=1) * np.sqrt(24 * 365)) if len(returns) > 1 else 0.0
    volume_mean = frame["volume"].rolling(window).mean().iloc[-1]
    volume_std = frame["volume"].rolling(window).std(ddof=1).iloc[-1]
    volume_z = float((frame["volume"].iloc[-1] - volume_mean) / max(volume_std, 1e-12)) if np.isfinite(volume_std) else 0.0
    if realized_vol < 0.50 and abs(funding_rate) < 0.0005:
        regime = Regime.QUIET
        confirmations, z_entry = 3, 2.0
        weights = {"momentum": 1.0, "market_making": 1.0, "statistical_arbitrage": 0.8, "perpetual_hedge": 0.7}
    elif realized_vol > 1.00 or abs(funding_rate) > 0.0015 or volume_z > 3.0:
        regime = Regime.TURBULENT
        confirmations, z_entry = 4, 2.5
        weights = {"momentum": 0.5, "market_making": 0.4, "statistical_arbitrage": 1.0, "perpetual_hedge": 1.0}
    else:
        regime = Regime.TRANSITIONAL
        confirmations, z_entry = 4, 2.25
        weights = {"momentum": 0.6, "market_making": 0.6, "statistical_arbitrage": 0.8, "perpetual_hedge": 0.8}
    return RegimeSnapshot(regime, realized_vol, volume_z, abs(funding_rate), confirmations, z_entry, weights)
