"""Shadow-trading promotion and live-drift gates."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ShadowGate:
    accepted: bool
    reasons: tuple[str, ...]


def compare_shadow_to_backtest(*, shadow_win_rate: float, backtest_win_rate: float, shadow_pnl: float, backtest_pnl: float, max_win_rate_gap: float = 0.10, max_pnl_gap_pct: float = 0.25, min_shadow_trades: int = 30, shadow_trades: int) -> ShadowGate:
    reasons: list[str] = []
    if shadow_trades < min_shadow_trades:
        reasons.append("shadow_sample_too_small")
    if abs(shadow_win_rate - backtest_win_rate) > max_win_rate_gap:
        reasons.append("shadow_win_rate_drift")
    if backtest_pnl > 0 and shadow_pnl < backtest_pnl * (1.0 - max_pnl_gap_pct):
        reasons.append("shadow_pnl_drift")
    return ShadowGate(not reasons, tuple(reasons))


def drift_action(gate: ShadowGate, *, currently_live: bool) -> str:
    if gate.accepted and not currently_live:
        return "eligible_for_reviewed_promotion"
    if not gate.accepted and currently_live:
        return "demote_to_shadow"
    return "remain_shadow" if not gate.accepted else "remain_live"
