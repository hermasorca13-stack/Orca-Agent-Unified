"""Unified Section 22 layer: calibration proposals plus cross-system immune memory."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from trading_bot.analytics.calibration22 import BayesianCalibrator, CalibrationProposal, CalibrationResult
from trading_bot.analytics.immune_memory22 import ImmuneMatch, ImmuneMemory, ImmuneObservation
from trading_bot.risk.kill_switch import KillSwitch
from trading_bot.storage.audit import AuditLog


@dataclass(frozen=True)
class Section22TradeResult:
    immune: ImmuneObservation
    screen: ImmuneMatch
    halted: bool


class Section22Layer:
    """Review-only calibration; immune memory may reject/reduce, never increase exposure."""

    def __init__(self, *, audit: AuditLog | None = None, kill_switch: KillSwitch | None = None, calibrator: BayesianCalibrator | None = None, immune: ImmuneMemory | None = None):
        self.audit = audit
        self.kill_switch = kill_switch
        self.calibrator = calibrator or BayesianCalibrator()
        self.immune = immune or ImmuneMemory()
        self.halted = False

    def _audit(self, event: str, payload: object) -> None:
        if self.audit is not None:
            self.audit.write(event, payload)

    def stop_if_killed(self) -> bool:
        killed = bool(self.kill_switch and self.kill_switch.status().get("halted", False))
        if killed:
            self.halted = True
        return self.halted

    def propose(self, *, context: str = "unknown") -> CalibrationProposal | None:
        if self.stop_if_killed():
            return None
        proposal = self.calibrator.propose(context=context)
        if proposal:
            self._audit("section22_calibration_proposal", proposal)
        return proposal

    def record_calibration(self, proposal: CalibrationProposal, *, score: float, cpcv_pass: bool, pbo: float, dsr: float, shadow_pass: bool) -> CalibrationResult:
        if self.stop_if_killed():
            raise RuntimeError("section22 halted by kill switch")
        result = self.calibrator.record_result(proposal, score=score, cpcv_pass=cpcv_pass, pbo=pbo, dsr=dsr, shadow_pass=shadow_pass)
        self._audit("section22_calibration_result", result)
        return result

    def screen_signal(self, features: tuple[float, ...] | list[float]) -> ImmuneMatch:
        if self.stop_if_killed():
            return ImmuneMatch(True, None, 1.0, 0.0, True, "section22_kill_switch")
        return self.immune.screen(features)

    def on_trade_closed(self, *, features: tuple[float, ...] | list[float], pnl: float, risk_budget: float, expected_edge: float, network_stress: bool = False) -> Section22TradeResult:
        if self.stop_if_killed():
            raise RuntimeError("section22 halted by kill switch")
        observation = self.immune.confirm_outcome(features, pnl=pnl, risk_budget=risk_budget, expected_edge=expected_edge, network_stress=network_stress)
        match = self.immune.screen(features) if features else ImmuneMatch(False, None, 0.0, 1.0, False, "empty_features")
        self._audit("section22_immune_observation", observation)
        if observation.antigen:
            self._audit("section22_antigen_detector", {"features": tuple(features), "network_stress": network_stress})
        return Section22TradeResult(observation, match, False)

    def decay_memory(self, *, shadow_pass: bool, reactivations: set[str] | None = None) -> None:
        if self.stop_if_killed():
            return
        self.immune.decay_cycle(shadow_pass=shadow_pass, reactivations=reactivations)
        self._audit("section22_immune_decay", {"shadow_pass": shadow_pass, "reactivations": sorted(reactivations or set())})

    def halt(self, reason: str = "section22_kill_switch") -> dict:
        if self.kill_switch is None:
            self.halted = True
            self._audit("section22_halted", {"reason": reason})
            return {"halted": True, "reason": reason}
        state = self.kill_switch.trigger(reason, close_positions=True)
        self.halted = True
        self._audit("section22_halted", state)
        return state
