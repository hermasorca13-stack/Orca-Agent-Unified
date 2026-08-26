"""Operational monitoring loop primitives."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from trading_bot.models import RiskSnapshot
from trading_bot.risk.gates import RiskEngine
from trading_bot.risk.kill_switch import KillSwitch
from trading_bot.storage.audit import AuditLog


@dataclass(frozen=True)
class MonitorResult:
    ok: bool
    reasons: tuple[str, ...]
    checked_at: datetime


class OperationalMonitor:
    def __init__(self, risk: RiskEngine, kill_switch: KillSwitch, audit: AuditLog):
        self.risk = risk
        self.kill_switch = kill_switch
        self.audit = audit

    def check(self, snapshot: RiskSnapshot) -> MonitorResult:
        gate = self.risk.emergency_gate(snapshot)
        result = MonitorResult(gate.allowed, gate.reasons, datetime.now(timezone.utc))
        self.audit.write("monitor_check", result)
        if not result.ok:
            self.kill_switch.trigger(";".join(result.reasons))
            self.audit.write("kill_switch_triggered", {"reasons": result.reasons})
        return result
