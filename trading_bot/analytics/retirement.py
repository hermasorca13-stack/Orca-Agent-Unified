"""Continuous, reversible retirement of weak strategy-symbol pairs."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetirementDecision:
    key: str
    previous_weight: float
    new_weight: float
    status: str
    reasons: tuple[str, ...]


def evaluate(key: str, *, previous_weight: float, win_rate: float, sharpe: float, pbo: float, consecutive_bad_windows: int, min_win_rate: float = 0.45, min_sharpe: float = 0.0, max_pbo: float = 0.50, bad_window_limit: int = 3, reduction_step: float = 0.05) -> RetirementDecision:
    reasons = []
    if win_rate < min_win_rate:
        reasons.append("win_rate_below_floor")
    if sharpe < min_sharpe:
        reasons.append("sharpe_below_floor")
    if pbo > max_pbo:
        reasons.append("pbo_above_ceiling")
    if len(reasons) >= 2 and consecutive_bad_windows >= bad_window_limit:
        new_weight = max(0.0, previous_weight - reduction_step)
        status = "watchlist" if new_weight > 0 else "retired"
    else:
        new_weight, status = previous_weight, "active"
    return RetirementDecision(key, previous_weight, new_weight, status, tuple(reasons))
