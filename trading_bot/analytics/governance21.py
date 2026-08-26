"""Section 21 governance: review-only candidates and fail-closed controls."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from trading_bot.risk.kill_switch import KillSwitch


@dataclass(frozen=True)
class GovernanceDecision:
    eligible_for_review: bool
    execution_eligible: bool
    reasons: tuple[str, ...]
    action: str


class Section21Governance:
    """The layer can recommend review or tightening, never authorize Live."""

    def __init__(self, kill_switch: KillSwitch | None = None):
        self.kill_switch = kill_switch
        self.structural_review_marker = False

    def mark_structural_change(self) -> None:
        self.structural_review_marker = True

    def evaluate(self, *, causal_pass: bool, cpcv_pass: bool, pbo: float, dsr: float, shadow_pass: bool, tail_pass: bool, drift_warning: bool = False) -> GovernanceDecision:
        reasons: list[str] = []
        if not causal_pass:
            reasons.append("causal_validation_failed")
        if not cpcv_pass:
            reasons.append("cpcv_failed")
        if pbo > 0.05:
            reasons.append("pbo_above_threshold")
        if dsr <= 0.0:
            reasons.append("deflated_sharpe_failed")
        if not shadow_pass:
            reasons.append("shadow_gate_failed")
        if not tail_pass:
            reasons.append("tail_risk_failed")
        if drift_warning:
            reasons.append("concept_drift_requires_section20_review")
        if self.structural_review_marker:
            reasons.append("structural_review_required")
        eligible = not reasons
        return GovernanceDecision(eligible, False, tuple(reasons), "review_only_no_direct_live_authority")

    def halt_if_kill_switch(self, *, reason: str = "section21_kill_switch") -> bool:
        if self.kill_switch is None:
            return False
        return bool(self.kill_switch.status().get("halted", False))

    def enforce_halt(self, *, reason: str = "section21_kill_switch") -> dict:
        if self.kill_switch is None:
            raise RuntimeError("kill switch is required for enforcement")
        return self.kill_switch.trigger(reason, close_positions=True)
