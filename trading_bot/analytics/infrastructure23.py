"""Section 23 physical execution constraints and infrastructure budgets."""
from __future__ import annotations

from dataclasses import dataclass
from time import monotonic


@dataclass(frozen=True)
class ComputeBudget:
    task: str
    cpu_cores: int
    memory_gb: float
    gpu_count: int
    node_role: str


DEFAULT_BUDGETS = (
    ComputeBudget("live_execution", 2, 4.0, 0, "live_trading_node"),
    ComputeBudget("section20_adaptation", 4, 8.0, 0, "research_compute_node"),
    ComputeBudget("section21_discovery_stress", 8, 16.0, 0, "research_compute_node"),
    ComputeBudget("section22_calibration_immune", 4, 8.0, 0, "research_compute_node"),
    ComputeBudget("deep_learning_optional", 8, 16.0, 1, "research_compute_node"),
)


@dataclass(frozen=True)
class NodeAssignment:
    node_id: str
    role: str
    allowed_tasks: tuple[str, ...]


@dataclass(frozen=True)
class LatencySnapshot:
    node_id: str
    samples: int
    p95_ms: float
    healthy: bool
    reason: str


class InfrastructureGuard:
    def __init__(self, *, latency_limit_ms: float = 500.0):
        self.latency_limit_ms = latency_limit_ms
        self.samples: dict[str, list[float]] = {}

    def validate_separation(self, assignments: list[NodeAssignment]) -> None:
        live_nodes = {assignment.node_id for assignment in assignments if assignment.role == "live_trading_node"}
        research_nodes = {assignment.node_id for assignment in assignments if assignment.role == "research_compute_node"}
        overlap = live_nodes & research_nodes
        if overlap:
            raise ValueError(f"live and research roles share nodes: {sorted(overlap)}")
        for assignment in assignments:
            if assignment.role == "live_trading_node" and any(task not in {"live_execution", "kill_switch", "market_monitoring"} for task in assignment.allowed_tasks):
                raise ValueError("live node has non-execution task")

    def record_latency(self, node_id: str, latency_ms: float) -> LatencySnapshot:
        self.samples.setdefault(node_id, []).append(max(0.0, float(latency_ms)))
        values = sorted(self.samples[node_id])
        index = min(len(values) - 1, int(round(0.95 * (len(values) - 1))))
        p95 = values[index]
        healthy = p95 <= self.latency_limit_ms
        return LatencySnapshot(node_id, len(values), p95, healthy, "ok" if healthy else "kill_switch_required")

    def budget(self, task: str) -> ComputeBudget:
        for budget in DEFAULT_BUDGETS:
            if budget.task == task:
                return budget
        raise KeyError(task)
