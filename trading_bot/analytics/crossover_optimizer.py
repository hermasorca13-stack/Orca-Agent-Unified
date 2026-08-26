"""Crossover-based optimizer that emits signals only on threshold crossings."""
from __future__ import annotations

from itertools import product
from typing import Callable, Iterable

import pandas as pd

from trading_bot.analytics.backtest import run_backtest
from trading_bot.analytics.optimizer import CandidateResult


def crossover_signal(parameters: dict[str, int | float]) -> Callable[[pd.DataFrame], float | None]:
    fast, slow = int(parameters["fast"]), int(parameters["slow"])
    gap_bps = float(parameters.get("gap_bps", 0.0))
    def signal(history: pd.DataFrame) -> float | None:
        if len(history) < slow + 1:
            return None
        fast_ma = history["close"].rolling(fast).mean()
        slow_ma = history["close"].rolling(slow).mean()
        current = float((fast_ma.iloc[-1] - slow_ma.iloc[-1]) / slow_ma.iloc[-1] * 10_000)
        previous = float((fast_ma.iloc[-2] - slow_ma.iloc[-2]) / slow_ma.iloc[-2] * 10_000)
        if previous <= gap_bps < current:
            return 1.0
        if previous >= -gap_bps > current:
            return -1.0
        return None
    return signal


def optimize_crossover(frame: pd.DataFrame, *, fast_values: Iterable[int] = (5, 10, 15, 20), slow_values: Iterable[int] = (40, 60, 80, 100), gap_values: Iterable[float] = (0, 5, 10, 20, 30), min_trades: int = 30) -> CandidateResult:
    candidates = []
    for fast, slow, gap_bps in product(fast_values, slow_values, gap_values):
        if fast >= slow or slow + 220 > len(frame):
            continue
        parameters = {"fast": fast, "slow": slow, "gap_bps": gap_bps}
        result = run_backtest(frame, crossover_signal(parameters))
        accepted = result.trades >= min_trades and result.net_pnl > 0 and result.profit_factor > 1.0
        candidates.append(CandidateResult(parameters, result, accepted))
    if not candidates:
        raise ValueError("no valid crossover candidates")
    viable = [candidate for candidate in candidates if candidate.accepted]
    return max(viable or candidates, key=lambda item: (item.result.win_rate, item.result.profit_factor, item.result.net_pnl))
