"""Walk-forward-safe parameter search for cumulative strategy improvement."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Callable, Iterable

import pandas as pd

from trading_bot.analytics.backtest import BacktestResult, run_backtest


@dataclass(frozen=True)
class CandidateResult:
    parameters: dict[str, int]
    result: BacktestResult
    accepted: bool


def sma_signal(parameters: dict[str, int | float]) -> Callable[[pd.DataFrame], float | None]:
    fast, slow = parameters["fast"], parameters["slow"]
    gap_bps = float(parameters.get("gap_bps", 0.0))
    def signal(history: pd.DataFrame) -> float | None:
        if len(history) < slow:
            return None
        fast_value = history["close"].rolling(fast).mean().iloc[-1]
        slow_value = history["close"].rolling(slow).mean().iloc[-1]
        gap = (fast_value - slow_value) / slow_value * 10_000
        if abs(gap) < gap_bps:
            return None
        return 1.0 if gap > 0 else -1.0
    return signal


def optimize_sma(frame: pd.DataFrame, *, fast_values: Iterable[int] = (5, 10, 15, 20), slow_values: Iterable[int] = (30, 50, 80, 100), gap_values: Iterable[float] = (0.0, 5.0, 10.0, 20.0, 30.0), min_trades: int = 30) -> CandidateResult:
    candidates: list[CandidateResult] = []
    for fast, slow, gap_bps in product(fast_values, slow_values, gap_values):
        if fast >= slow or slow + 220 > len(frame):
            continue
        parameters = {"fast": fast, "slow": slow, "gap_bps": gap_bps}
        result = run_backtest(frame, sma_signal(parameters))
        accepted = result.trades >= min_trades and result.net_pnl > 0 and result.profit_factor > 1.0
        candidates.append(CandidateResult(parameters, result, accepted))
    if not candidates:
        raise ValueError("no valid optimizer candidates")
    viable = [candidate for candidate in candidates if candidate.accepted]
    pool = viable or candidates
    return max(pool, key=lambda candidate: (candidate.result.win_rate, candidate.result.profit_factor, candidate.result.net_pnl))
