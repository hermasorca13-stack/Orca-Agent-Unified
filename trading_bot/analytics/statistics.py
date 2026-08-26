"""Statistical pair validation with transparent, dependency-light calculations."""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from trading_bot.models import PairValidation


def _ols_hedge_ratio(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    matrix = np.column_stack([np.ones(len(x)), x])
    intercept, slope = np.linalg.lstsq(matrix, y, rcond=None)[0]
    return float(intercept), float(slope)


def _adf_like_stat(residuals: np.ndarray) -> float:
    """ADF-style t statistic for Δe_t = alpha + rho*e_(t-1) + error."""
    if len(residuals) < 20:
        return float("nan")
    lagged = residuals[:-1]
    delta = np.diff(residuals)
    matrix = np.column_stack([np.ones(len(lagged)), lagged])
    coefficient = np.linalg.lstsq(matrix, delta, rcond=None)[0]
    fitted = matrix @ coefficient
    degrees = max(len(delta) - matrix.shape[1], 1)
    variance = float(np.sum((delta - fitted) ** 2) / degrees)
    cov = variance * np.linalg.pinv(matrix.T @ matrix)
    se = math.sqrt(max(float(cov[1, 1]), 1e-18))
    return float(coefficient[1] / se)


def validate_pair(series_a: Sequence[float], series_b: Sequence[float], *, symbol_a: str, symbol_b: str, z_window: int = 60) -> PairValidation:
    x = np.asarray(series_a, dtype=float)
    y = np.asarray(series_b, dtype=float)
    if len(x) != len(y) or len(x) < max(z_window, 100):
        raise ValueError("pair validation requires equal series with at least 100 observations")
    if np.any(~np.isfinite(x)) or np.any(~np.isfinite(y)):
        raise ValueError("pair validation received non-finite observations")
    _, hedge_ratio = _ols_hedge_ratio(np.log(x), np.log(y))
    spread = np.log(y) - hedge_ratio * np.log(x)
    mean = float(np.mean(spread[-z_window:]))
    std = float(np.std(spread[-z_window:], ddof=0))
    z = float((spread[-1] - mean) / std) if std > 0 else 0.0
    correlation = float(np.corrcoef(np.diff(np.log(x)), np.diff(np.log(y)))[0, 1])
    adf_stat = _adf_like_stat(spread)
    stationary = bool(np.isfinite(adf_stat) and adf_stat < -2.86)
    cointegrated = bool(stationary and correlation >= 0.60)
    reason = f"adf_stat={adf_stat:.3f}; corr={correlation:.3f}; z={z:.3f}"
    return PairValidation(symbol_a, symbol_b, hedge_ratio, mean, std, z, cointegrated, stationary, correlation, len(x), reason)
