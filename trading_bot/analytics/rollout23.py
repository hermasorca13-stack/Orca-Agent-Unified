"""Section 23 staged capital and execution-code change governance."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CapitalRampDecision:
    stage: str
    capital_fraction: float
    accepted: bool
    reason: str
    live_authority: bool = False


class CapitalRamp:
    def __init__(self, *, pilot_fraction: float = 0.01, slippage_tolerance_bps: float = 5.0, min_observations: int = 30):
        self.pilot_fraction = min(0.05, max(0.0, pilot_fraction))
        self.slippage_tolerance_bps = max(0.0, slippage_tolerance_bps)
        self.min_observations = max(1, min_observations)

    def shadow_to_pilot(self, *, shadow_pass: bool) -> CapitalRampDecision:
        if not shadow_pass:
            return CapitalRampDecision("shadow", 0.0, False, "shadow_gate_required")
        return CapitalRampDecision("pilot_review_required", self.pilot_fraction, False, "human_approval_and_external_account_required")

    def pilot_to_full(self, *, observations: int, actual_slippage_bps: float, expected_slippage_bps: float, new_immune_detector: bool) -> CapitalRampDecision:
        deviation = abs(actual_slippage_bps - expected_slippage_bps)
        accepted = observations >= self.min_observations and deviation <= self.slippage_tolerance_bps and not new_immune_detector
        reason = "quantitative_ramp_criteria_met_review_required" if accepted else "return_to_pilot_or_halt_ramp"
        return CapitalRampDecision("full_review_required" if accepted else "pilot_or_halt", 1.0 if accepted else self.pilot_fraction, accepted, reason)

    def rollback(self, *, actual_slippage_bps: float, expected_slippage_bps: float) -> CapitalRampDecision:
        return CapitalRampDecision("rollback", self.pilot_fraction, False, f"slippage_deviation={abs(actual_slippage_bps - expected_slippage_bps):.6f}_exceeded_or_review_requested")


@dataclass(frozen=True)
class CodeReleaseDecision:
    staging_pass: bool
    independent_review: bool
    canary_pass: bool
    rollback_version: str
    accepted: bool
    reason: str


class CodeReleaseGovernance:
    def __init__(self, *, stable_version: str):
        if not stable_version.strip():
            raise ValueError("stable rollback version is required")
        self.stable_version = stable_version

    def review(self, *, staging_pass: bool, independent_review: bool, canary_pass: bool) -> CodeReleaseDecision:
        accepted = bool(staging_pass and independent_review and canary_pass)
        return CodeReleaseDecision(staging_pass, independent_review, canary_pass, self.stable_version, accepted, "release_review_passed" if accepted else "release_blocked_until_staging_review_and_canary_pass")
