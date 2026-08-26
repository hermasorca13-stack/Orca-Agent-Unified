"""Cross-source market-data validation and point-in-time archival controls."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path


@dataclass(frozen=True)
class SourcePriority:
    data_type: str
    sources: tuple[str, ...]


@dataclass(frozen=True)
class CrossSourceResult:
    data_type: str
    source_values: dict[str, float]
    median: float
    max_deviation: float
    accepted: bool
    selected_source: str | None
    reason: str


class DataQualityGate:
    def __init__(self, *, deviation_limit: float = 0.005, priorities: tuple[SourcePriority, ...] = ()):
        self.deviation_limit = max(0.0, deviation_limit)
        self.priorities = {priority.data_type: priority.sources for priority in priorities}

    def compare(self, data_type: str, values: dict[str, float]) -> CrossSourceResult:
        finite = {source: float(value) for source, value in values.items() if value == value and abs(float(value)) != float("inf")}
        if len(finite) < 2:
            return CrossSourceResult(data_type, finite, 0.0, float("inf"), False, None, "at_least_two_independent_sources_required")
        ordered = list(finite.values())
        ordered.sort()
        median = ordered[len(ordered) // 2] if len(ordered) % 2 else (ordered[len(ordered) // 2 - 1] + ordered[len(ordered) // 2]) / 2.0
        max_deviation = max(abs(value - median) / max(abs(median), 1e-12) for value in ordered)
        accepted = max_deviation <= self.deviation_limit
        selected = next((source for source in self.priorities.get(data_type, ()) if source in finite), None)
        if selected is None and accepted:
            selected = min(finite, key=lambda source: abs(finite[source] - median))
        return CrossSourceResult(data_type, finite, median, max_deviation, accepted, selected, "within_cross_source_deviation" if accepted else "reject_bad_tick_or_source_conflict")

    def archive_point_in_time(self, path: Path, *, data_type: str, payload: object, received_at: datetime | None = None) -> dict[str, str]:
        received_at = received_at or datetime.now(timezone.utc)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        record = {"received_at": received_at.isoformat(), "data_type": data_type, "sha256": sha256(encoded.encode("utf-8")).hexdigest(), "payload": payload}
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        return {"received_at": record["received_at"], "sha256": record["sha256"]}
