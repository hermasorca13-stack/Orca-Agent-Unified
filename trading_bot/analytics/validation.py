"""Validation utilities for research and pre-deployment gates."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

import numpy as np
import pandas as pd

from trading_bot.analytics.backtest import BacktestResult, run_backtest


@dataclass(frozen=True)
class ValidationReport:
    in_sample: BacktestResult
    out_of_sample: BacktestResult
    walk_forward: tuple[BacktestResult, ...]
    monte_carlo_max_drawdown_p95: float
    stress_results: dict[str, float]
    accepted: bool


def out_of_sample(frame: pd.DataFrame, signal_fn: Callable[[pd.DataFrame], float | None], train_fraction: float = 0.70) -> tuple[BacktestResult, BacktestResult]:
    split = int(len(frame) * train_fraction)
    split = max(220, min(split, len(frame) - 2))
    in_sample = run_backtest(frame.iloc[:split], signal_fn)
    out_sample = run_backtest(frame.iloc[split - 220 :], signal_fn)
    return in_sample, out_sample


def walk_forward(frame: pd.DataFrame, signal_fn: Callable[[pd.DataFrame], float | None], *, train_size: int = 220, test_size: int = 60) -> tuple[BacktestResult, ...]:
    results = []
    start = 0
    while start + train_size + test_size <= len(frame):
        test = frame.iloc[start : start + train_size + test_size]
        results.append(run_backtest(test, signal_fn))
        start += test_size
    return tuple(results)


def monte_carlo_max_drawdown(returns: Iterable[float], *, paths: int = 1000, seed: int = 7) -> float:
    values = np.asarray(tuple(returns), dtype=float)
    if len(values) < 2:
        return 0.0
    rng = np.random.default_rng(seed)
    sampled = rng.choice(values, size=(paths, len(values)), replace=True)
    curves = np.cumprod(1.0 + sampled, axis=1)
    peaks = np.maximum.accumulate(curves, axis=1)
    drawdowns = (peaks - curves) / np.maximum(peaks, 1e-12)
    return float(np.quantile(drawdowns.max(axis=1), 0.95))


def stress_suite(frame: pd.DataFrame, signal_fn: Callable[[pd.DataFrame], float | None]) -> dict[str, float]:
    results: dict[str, float] = {}
    baseline = run_backtest(frame, signal_fn, slippage_bps=2.0)
    results["baseline_net_pnl"] = baseline.net_pnl
    results["wide_spread_net_pnl"] = run_backtest(frame, signal_fn, slippage_bps=20.0).net_pnl
    results["high_fee_net_pnl"] = run_backtest(frame, signal_fn, fee_bps=20.0).net_pnl
    halted = frame.copy()
    halted.iloc[len(halted) // 2 :, halted.columns.get_loc("volume")] = 0.0
    results["data_interruption_net_pnl"] = run_backtest(halted, signal_fn).net_pnl
    return results
