"""Unified Section 23 physical, execution-quality and legal boundary layer."""
from __future__ import annotations

from dataclasses import dataclass

from trading_bot.analytics.capacity23 import CapacityAnalyzer, CapacityReport
from trading_bot.analytics.compliance23 import LegalStatus
from trading_bot.analytics.data_quality23 import CrossSourceResult, DataQualityGate
from trading_bot.analytics.execution_quality23 import DefiExecutionGuard, SmartOrderRouter, ToxicityReport, VenueQuote, protect_market_making, validate_defi_execution, vpin
from trading_bot.analytics.infrastructure23 import InfrastructureGuard, LatencySnapshot, NodeAssignment
from trading_bot.analytics.rollout23 import CapitalRamp, CapitalRampDecision, CodeReleaseGovernance, CodeReleaseDecision
from trading_bot.risk.kill_switch import KillSwitch
from trading_bot.storage.audit import AuditLog


@dataclass(frozen=True)
class Section23ExecutionDecision:
    allowed_after_prior_gates: bool
    quote_allowed: bool
    selected_venue: str | None
    order_fraction: float
    reason: str
    live_authority: bool = False


class Section23Layer:
    """The layer constrains execution after prior signal/risk gates; it never creates authority."""

    def __init__(self, *, audit: AuditLog | None = None, kill_switch: KillSwitch | None = None):
        self.audit = audit
        self.kill_switch = kill_switch
        self.infrastructure = InfrastructureGuard()
        self.capacity = CapacityAnalyzer()
        self.data_quality = DataQualityGate()
        self.router = SmartOrderRouter()
        self.ramp = CapitalRamp()
        self.halted = False
        self.legal_hold = True

    def _audit(self, event: str, payload: object) -> None:
        if self.audit:
            self.audit.write(event, payload)

    def stopped(self) -> bool:
        if self.halted:
            return True
        if self.kill_switch and self.kill_switch.status().get("halted", False):
            self.halted = True
        return self.halted

    def configure_nodes(self, assignments: list[NodeAssignment]) -> None:
        self.infrastructure.validate_separation(assignments)
        self._audit("section23_node_separation_validated", assignments)

    def record_latency(self, node_id: str, latency_ms: float) -> LatencySnapshot:
        snapshot = self.infrastructure.record_latency(node_id, latency_ms)
        self._audit("section23_execution_latency", snapshot)
        if not snapshot.healthy:
            self.halt("execution_latency_limit_exceeded")
        return snapshot

    def set_legal_status(self, status: LegalStatus) -> None:
        self.legal_hold = not status.allowed_to_trade
        self._audit("section23_legal_status", status)

    def execution_decision(self, *, prior_gates_allowed: bool, toxicity: ToxicityReport, venues: list[VenueQuote], required_notional: float, capacity: CapacityReport | None = None, defi: DefiExecutionGuard | None = None) -> Section23ExecutionDecision:
        if self.stopped():
            return Section23ExecutionDecision(False, False, None, 0.0, "kill_switch_active")
        if self.legal_hold:
            return Section23ExecutionDecision(False, False, None, 0.0, "legal_compliance_hold")
        if not prior_gates_allowed:
            return Section23ExecutionDecision(False, False, None, 0.0, "prior_section_gates_required")
        quote = protect_market_making(toxicity)
        selected = self.router.choose(venues, required_notional=required_notional)
        if not quote.quote_allowed or selected is None or (capacity is not None and not capacity.accepted) or (defi is not None and not defi.allowed):
            return Section23ExecutionDecision(False, quote.quote_allowed, selected.venue if selected else None, 0.0, "execution_quality_or_capacity_rejected")
        fraction = min(1.0, capacity.weight_multiplier if capacity else 1.0)
        decision = Section23ExecutionDecision(True, True, selected.venue, fraction, "execution_constraints_passed_review_only")
        self._audit("section23_execution_decision", decision)
        return decision

    def compare_sources(self, data_type: str, values: dict[str, float]) -> CrossSourceResult:
        result = self.data_quality.compare(data_type, values)
        self._audit("section23_cross_source_check", result)
        return result

    def defi_guard(self, *, private_rpc: bool, slippage_bps: float, mev_cost_bps: float) -> DefiExecutionGuard:
        result = validate_defi_execution(private_rpc=private_rpc, slippage_bps=slippage_bps, mev_cost_bps=mev_cost_bps)
        self._audit("section23_defi_execution_guard", result)
        return result

    def ramp_decision(self, *, shadow_pass: bool) -> CapitalRampDecision:
        return self.ramp.shadow_to_pilot(shadow_pass=shadow_pass)

    def review_code_release(self, *, stable_version: str, staging_pass: bool, independent_review: bool, canary_pass: bool) -> CodeReleaseDecision:
        return CodeReleaseGovernance(stable_version=stable_version).review(staging_pass=staging_pass, independent_review=independent_review, canary_pass=canary_pass)

    def halt(self, reason: str = "section23_kill_switch") -> dict:
        self.halted = True
        if self.kill_switch:
            state = self.kill_switch.trigger(reason, close_positions=True)
        else:
            state = {"halted": True, "reason": reason}
        self._audit("section23_halted", state)
        return state
