"""Cross-venue stress contagion graph with exposure-reduction-only actions."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ContagionAssessment:
    venues: tuple[str, ...]
    centrality: dict[str, float]
    affected: tuple[str, ...]
    exposure_multiplier: float
    action: str


class ContagionGraph:
    def __init__(self, *, correlation_threshold: float = 0.70, stress_threshold: float = 2.0, reduction: float = 0.50):
        self.correlation_threshold = correlation_threshold
        self.stress_threshold = stress_threshold
        self.reduction = min(1.0, max(0.0, reduction))

    def assess(self, stress_history: dict[str, list[float]]) -> ContagionAssessment:
        venues = tuple(stress_history)
        if not venues:
            return ContagionAssessment((), {}, (), 1.0, "no_data")
        matrix = np.array([stress_history[venue] for venue in venues], dtype=float)
        if matrix.shape[0] == 1:
            centrality = {venues[0]: 1.0}
            affected = (venues[0],) if np.nanmean(matrix[0]) >= self.stress_threshold else ()
        else:
            corr = np.nan_to_num(np.corrcoef(matrix), nan=0.0)
            centrality = {venue: float(np.mean(np.abs(corr[i]))) for i, venue in enumerate(venues)}
            stressed = np.array([np.nanmean(row) >= self.stress_threshold for row in matrix])
            linked = (corr >= self.correlation_threshold).any(axis=1)
            affected = tuple(venue for i, venue in enumerate(venues) if stressed[i] and (linked[i] or stressed.sum() >= 2))
        if len(affected) >= 2:
            return ContagionAssessment(venues, centrality, affected, 1.0 - self.reduction, "reduce_exposure_and_prioritize_liquidity_exit")
        return ContagionAssessment(venues, centrality, affected, 1.0, "monitor")

    def liquidity_exit_order(self, assessment: ContagionAssessment) -> tuple[str, ...]:
        return tuple(sorted(assessment.affected, key=lambda venue: assessment.centrality.get(venue, 0.0), reverse=True))
