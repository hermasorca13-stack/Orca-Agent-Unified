"""Online Bayesian mixture of experts and changepoint alarm."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class ExpertBelief:
    name: str
    alpha: float = 1.0
    beta: float = 1.0

    @property
    def expected_accuracy(self) -> float:
        return self.alpha / (self.alpha + self.beta)


@dataclass(frozen=True)
class ChangepointAlarm:
    detected: bool
    score: float
    reason: str


class OnlineMixture:
    def __init__(self, expert_names: tuple[str, ...] = ("statistical", "tree", "neural"), *, min_history: int = 20, changepoint_z: float = 3.0):
        self.experts = {name: ExpertBelief(name) for name in expert_names}
        self.min_history = min_history
        self.changepoint_z = changepoint_z
        self.errors: list[float] = []

    def update(self, outcomes: dict[str, bool]) -> None:
        for name, correct in outcomes.items():
            if name not in self.experts:
                self.experts[name] = ExpertBelief(name)
            belief = self.experts[name]
            if correct:
                belief.alpha += 1.0
            else:
                belief.beta += 1.0
        if outcomes:
            self.errors.append(1.0 - sum(outcomes.values()) / len(outcomes))

    def predict(self, predictions: dict[str, float]) -> float:
        usable = {name: value for name, value in predictions.items() if name in self.experts}
        if not usable:
            raise ValueError("no registered expert predictions")
        weights = {name: self.experts[name].expected_accuracy for name in usable}
        denominator = sum(weights.values()) or 1.0
        return float(sum(weights[name] * float(usable[name]) for name in usable) / denominator)

    def changepoint(self) -> ChangepointAlarm:
        if len(self.errors) < self.min_history:
            return ChangepointAlarm(False, 0.0, "insufficient_history")
        split = len(self.errors) // 2
        left, right = np.asarray(self.errors[:split]), np.asarray(self.errors[split:])
        pooled = max(float(np.std(self.errors, ddof=1)), 1e-9)
        score = abs(float(right.mean() - left.mean())) / pooled
        return ChangepointAlarm(score >= self.changepoint_z, score, "rolling_error_mean_shift" if score >= self.changepoint_z else "stable")
