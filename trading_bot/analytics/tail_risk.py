"""Empirical CVaR and conservative EVT-style tail diagnostics."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class TailRiskReport:
    var: float
    cvar: float
    tail_mean: float
    observations: int
    accepted: bool


def cvar(returns: list[float] | np.ndarray, alpha: float = 0.95) -> float:
    values = np.asarray(returns, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) < 10:
        raise ValueError("CVaR requires at least 10 finite returns")
    losses = -values
    threshold = float(np.quantile(losses, alpha))
    tail = losses[losses >= threshold]
    return float(tail.mean())


def evt_tail_loss(returns: list[float] | np.ndarray, threshold_quantile: float = 0.90) -> float:
    values = np.asarray(returns, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) < 10:
        raise ValueError("EVT diagnostic requires at least 10 finite returns")
    losses = -values
    threshold = float(np.quantile(losses, threshold_quantile))
    excess = losses[losses > threshold] - threshold
    if len(excess) < 3:
        return float(losses.max())
    mean_excess = float(excess.mean())
    return float(threshold + mean_excess * (1.0 + len(excess) / len(losses)))


def report(returns: list[float] | np.ndarray, *, baseline_cvar: float | None = None, alpha: float = 0.95) -> TailRiskReport:
    values = np.asarray(returns, dtype=float)
    values = values[np.isfinite(values)]
    var = float(np.quantile(-values, alpha))
    conditional = cvar(values, alpha)
    evt = evt_tail_loss(values)
    accepted = baseline_cvar is None or conditional <= baseline_cvar * 2.0
    return TailRiskReport(var, conditional, evt, len(values), accepted)
