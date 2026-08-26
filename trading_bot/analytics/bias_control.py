"""Backtest-selection bias controls: purged folds, PBO and deflated Sharpe."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from statistics import NormalDist

import numpy as np


@dataclass(frozen=True)
class PurgedFold:
    train: np.ndarray
    test: np.ndarray


def purged_combinatorial_folds(n_samples: int, *, groups: int = 5, test_groups: int = 2, embargo: int = 5, label_horizon: int = 1) -> tuple[PurgedFold, ...]:
    if groups < 3 or test_groups < 1 or test_groups >= groups:
        raise ValueError("groups must be >= 3 and test_groups must be smaller than groups")
    boundaries = np.linspace(0, n_samples, groups + 1, dtype=int)
    folds: list[PurgedFold] = []
    for selected in combinations(range(groups), test_groups):
        test = np.concatenate([np.arange(boundaries[g], boundaries[g + 1]) for g in selected])
        mask = np.ones(n_samples, dtype=bool)
        mask[test] = False
        for start in test:
            left = max(0, start - label_horizon)
            right = min(n_samples, start + label_horizon + embargo + 1)
            mask[left:right] = False
        folds.append(PurgedFold(np.flatnonzero(mask), np.sort(test)))
    return tuple(folds)


def probability_backtest_overfitting(performance_matrix: np.ndarray) -> float:
    """Approximate PBO from strategy-by-fold returns using IS winner rank in OOS."""
    values = np.asarray(performance_matrix, dtype=float)
    if values.ndim != 2 or min(values.shape) < 2:
        raise ValueError("performance_matrix must contain at least two strategies and two folds")
    half = values.shape[1] // 2
    is_values, oos_values = values[:, :half], values[:, half:]
    is_winner = np.argmax(is_values.mean(axis=1))
    winner_oos = oos_values[is_winner].mean()
    return float(np.mean(oos_values.mean(axis=1) >= winner_oos))


def deflated_sharpe_ratio(sharpe: float, *, trials: int, observations: int, skew: float = 0.0, kurtosis: float = 3.0, annualization: float = 1.0) -> float:
    if observations < 2 or trials < 1:
        raise ValueError("observations and trials must be positive")
    expected_max = NormalDist().inv_cdf(max(1e-6, min(1 - 1e-6, 1.0 - 1.0 / trials))) * np.sqrt(annualization / observations)
    variance = max(1e-12, (1.0 - skew * sharpe + ((kurtosis - 1.0) / 4.0) * sharpe * sharpe) / observations)
    return float(NormalDist().cdf((sharpe - expected_max) / np.sqrt(variance)))
