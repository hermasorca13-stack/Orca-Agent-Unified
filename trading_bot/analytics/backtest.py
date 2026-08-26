"""Leakage-aware backtest utilities with explicit cost accounting."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BacktestResult:
    trades: int
    wins: int
    losses: int
    net_pnl: float
    gross_pnl: float
    total_costs: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    sharpe: float
    sortino: float


def run_backtest(frame: pd.DataFrame, signal_fn: Callable[[pd.DataFrame], float | None], *, initial_equity: float = 100_000.0, fee_bps: float = 4.0, slippage_bps: float = 2.0) -> BacktestResult:
    if len(frame) < 220:
        raise ValueError("backtest requires at least 220 bars for indicator warm-up")
    equity = float(initial_equity)
    curve = [equity]
    pnl_values: list[float] = []
    gross = 0.0
    costs = 0.0
    wins = losses = 0
    trades = 0
    for end in range(220, len(frame) - 1):
        history = frame.iloc[: end + 1].copy()
        direction = signal_fn(history)
        if direction is None or direction == 0:
            curve.append(equity)
            continue
        entry = float(frame["open"].iloc[end + 1])
        exit_price = float(frame["close"].iloc[end + 1])
        signed_return = direction * (exit_price - entry) / entry
        notional = equity * 0.01
        gross_pnl = notional * signed_return
        trade_cost = notional * (fee_bps + slippage_bps) / 10_000.0
        net = gross_pnl - trade_cost
        equity += net
        gross += gross_pnl
        costs += trade_cost
        pnl_values.append(net)
        trades += 1
        wins += int(net > 0)
        losses += int(net <= 0)
        curve.append(equity)
    series = np.asarray(pnl_values, dtype=float)
    curve_arr = np.asarray(curve, dtype=float)
    running_max = np.maximum.accumulate(curve_arr)
    drawdown = (running_max - curve_arr) / np.maximum(running_max, 1e-12)
    positive = series[series > 0].sum() if len(series) else 0.0
    negative = abs(series[series < 0].sum()) if len(series) else 0.0
    mean = float(series.mean()) if len(series) else 0.0
    std = float(series.std(ddof=1)) if len(series) > 1 else 0.0
    downside = float(series[series < 0].std(ddof=1)) if len(series[series < 0]) > 1 else 0.0
    return BacktestResult(trades, wins, losses, float(equity - initial_equity), gross, costs, float(drawdown.max(initial=0.0)), wins / trades if trades else 0.0, positive / negative if negative else float("inf"), mean / std * np.sqrt(252) if std else 0.0, mean / downside * np.sqrt(252) if downside else 0.0)
