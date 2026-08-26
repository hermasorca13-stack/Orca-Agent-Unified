"""Cross-system artificial immune memory for confirmed adverse trade fingerprints."""
from __future__ import annotations

from dataclasses import dataclass, replace
import numpy as np


@dataclass(frozen=True)
class ImmuneDetector:
    detector_id: str
    center: tuple[float, ...]
    radius: float
    severity: float = 1.0
    confirmed_hits: int = 0
    false_positives: int = 0
    dormant_cycles: int = 0
    network_stress_hits: int = 0

    @property
    def precision(self) -> float:
        return self.confirmed_hits / max(1, self.confirmed_hits + self.false_positives)


@dataclass(frozen=True)
class ImmuneMatch:
    matched: bool
    detector_id: str | None
    affinity: float
    size_multiplier: float
    reject: bool
    reason: str


@dataclass(frozen=True)
class ImmuneObservation:
    antigen: bool
    matched_detectors: tuple[str, ...]
    false_positive_detectors: tuple[str, ...]
    latency_cycles: int


def _distance(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    a, b = np.asarray(left, dtype=float), np.asarray(right, dtype=float)
    if a.shape != b.shape:
        raise ValueError("immune feature vectors must have equal dimensions")
    return float(np.linalg.norm(a - b))


class ImmuneMemory:
    """Shared memory across symbols and strategies; it can only tighten exposure."""

    def __init__(self, *, radius: float = 1.0, antigen_loss_threshold: float = 1.0, reject_affinity: float = 0.90, decay: float = 0.10):
        self.radius = max(1e-9, radius)
        self.antigen_loss_threshold = antigen_loss_threshold
        self.reject_affinity = min(1.0, max(0.0, reject_affinity))
        self.decay = min(1.0, max(0.0, decay))
        self.self_vectors: list[tuple[float, ...]] = []
        self.detectors: dict[str, ImmuneDetector] = {}
        self._next_id = 1
        self.observations: list[ImmuneObservation] = []

    def add_self(self, features: tuple[float, ...] | list[float]) -> None:
        vector = tuple(float(value) for value in features)
        if vector and all(np.isfinite(vector)):
            self.self_vectors.append(vector)

    def classify_antigen(self, *, pnl: float, risk_budget: float, expected_edge: float) -> bool:
        return pnl < -abs(risk_budget) * self.antigen_loss_threshold or expected_edge <= 0.0 and pnl < 0.0

    def _covered_by_self(self, center: tuple[float, ...]) -> bool:
        return any(_distance(center, vector) <= self.radius for vector in self.self_vectors)

    def generate_detector(self, center: tuple[float, ...], *, network_stress: bool = False) -> ImmuneDetector | None:
        center = tuple(float(value) for value in center)
        if not center or self._covered_by_self(center):
            return None
        detector = ImmuneDetector(f"detector-{self._next_id}", center, self.radius, severity=1.25 if network_stress else 1.0, network_stress_hits=1 if network_stress else 0)
        self._next_id += 1
        self.detectors[detector.detector_id] = detector
        return detector

    def screen(self, features: tuple[float, ...] | list[float]) -> ImmuneMatch:
        vector = tuple(float(value) for value in features)
        matches = []
        for detector in self.detectors.values():
            distance = _distance(vector, detector.center)
            affinity = max(0.0, 1.0 - distance / max(detector.radius, 1e-9))
            if affinity > 0.0:
                matches.append((affinity, detector))
        if not matches:
            return ImmuneMatch(False, None, 0.0, 1.0, False, "no_detector_match")
        affinity, detector = max(matches, key=lambda item: item[0] * item[1].severity)
        reject = affinity * detector.severity >= self.reject_affinity
        multiplier = max(0.0, min(1.0, 1.0 - affinity * detector.severity))
        return ImmuneMatch(True, detector.detector_id, affinity, multiplier, reject, "immune_reject" if reject else "immune_size_reduction")

    def confirm_outcome(self, features: tuple[float, ...] | list[float], *, pnl: float, risk_budget: float, expected_edge: float, network_stress: bool = False) -> ImmuneObservation:
        vector = tuple(float(value) for value in features)
        antigen = self.classify_antigen(pnl=pnl, risk_budget=risk_budget, expected_edge=expected_edge)
        match = self.screen(vector) if vector else ImmuneMatch(False, None, 0.0, 1.0, False, "empty_features")
        matched = (match.detector_id,) if match.detector_id else ()
        if antigen:
            if match.detector_id:
                detector = self.detectors[match.detector_id]
                confirmed = replace(detector, confirmed_hits=detector.confirmed_hits + 1, network_stress_hits=detector.network_stress_hits + int(network_stress), severity=min(2.0, detector.severity + (self.decay if network_stress else 0.0)))
                self.detectors[match.detector_id] = confirmed
                if confirmed.confirmed_hits >= 2:
                    self.clone_confirmed(match.detector_id)
            else:
                detector = self.generate_detector(vector, network_stress=network_stress)
                if detector is not None:
                    self.detectors[detector.detector_id] = replace(detector, confirmed_hits=1)
        elif match.detector_id:
            detector = self.detectors[match.detector_id]
            self.detectors[match.detector_id] = replace(detector, false_positives=detector.false_positives + 1)
        observation = ImmuneObservation(antigen, matched, matched if not antigen else (), 0)
        self.observations.append(observation)
        return observation

    def clone_confirmed(self, detector_id: str, *, mutation: float = 0.05) -> ImmuneDetector:
        detector = self.detectors[detector_id]
        noise = np.random.default_rng(detector.confirmed_hits + 22).normal(0.0, mutation, len(detector.center))
        clone = replace(detector, detector_id=f"{detector_id}-clone-{detector.confirmed_hits + 1}", center=tuple(np.asarray(detector.center) + noise), severity=min(2.0, detector.severity * 1.05), confirmed_hits=detector.confirmed_hits + 1)
        self.detectors[clone.detector_id] = clone
        return clone

    def decay_cycle(self, *, shadow_pass: bool, reactivations: set[str] | None = None) -> None:
        reactivations = reactivations or set()
        for detector_id, detector in list(self.detectors.items()):
            if detector_id in reactivations:
                self.detectors[detector_id] = replace(detector, dormant_cycles=0, severity=min(2.0, detector.severity + self.decay))
            elif shadow_pass:
                self.detectors[detector_id] = replace(detector, dormant_cycles=detector.dormant_cycles + 1, severity=max(0.0, detector.severity * (1.0 - self.decay)))

    def metrics(self) -> dict[str, float | int]:
        true_positive = sum(1 for observation in self.observations if observation.antigen and observation.matched_detectors)
        false_positive = sum(len(observation.false_positive_detectors) for observation in self.observations)
        antigen_count = sum(1 for observation in self.observations if observation.antigen)
        return {
            "observations": len(self.observations),
            "confirmed_antigens": antigen_count,
            "true_positive_detector_matches": true_positive,
            "false_positive_detector_matches": false_positive,
            "detector_precision": true_positive / max(1, true_positive + false_positive),
            "detectors_retained": len(self.detectors),
            "detectors_deleted": 0,
            "cross_system_sharing_latency_cycles": 0,
        }

    def network_adjust(self, detector_id: str, *, contagion_affected: bool) -> None:
        if detector_id not in self.detectors:
            raise KeyError(detector_id)
        detector = self.detectors[detector_id]
        if contagion_affected:
            self.detectors[detector_id] = replace(detector, network_stress_hits=detector.network_stress_hits + 1, severity=min(2.0, detector.severity + self.decay))
