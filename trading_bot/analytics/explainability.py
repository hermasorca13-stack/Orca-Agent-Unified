"""Model explainability and distribution-drift diagnostics."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class DriftReport:
    feature: str
    psi: float
    jsd: float
    warning: bool
    action: str


def permutation_importance(model, X, y, feature_names: list[str], *, repeats: int = 5, seed: int = 21) -> dict[str, float]:
    """Return normalized score drops; never changes the model or execution authority."""
    X = np.asarray(X)
    y = np.asarray(y)
    baseline = float(np.mean(np.asarray(model.predict(X)) == y))
    rng = np.random.default_rng(seed)
    drops: dict[str, float] = {}
    for column, name in enumerate(feature_names):
        scores = []
        for _ in range(repeats):
            permuted = X.copy()
            permuted[:, column] = X[rng.permutation(len(X)), column]
            scores.append(max(0.0, baseline - float(np.mean(np.asarray(model.predict(permuted)) == y))))
        drops[name] = float(np.mean(scores))
    total = sum(drops.values()) or 1.0
    return {name: value / total for name, value in drops.items()}


def _histogram(values: np.ndarray, edges: np.ndarray) -> np.ndarray:
    counts, _ = np.histogram(values, bins=edges)
    probability = counts.astype(float) + 1e-6
    return probability / probability.sum()


def drift_report(reference, current, feature: str, *, bins: int = 10, psi_threshold: float = 0.20, jsd_threshold: float = 0.10) -> DriftReport:
    reference = np.asarray(reference, dtype=float)
    current = np.asarray(current, dtype=float)
    reference = reference[np.isfinite(reference)]
    current = current[np.isfinite(current)]
    if len(reference) < 2 or len(current) < 2:
        return DriftReport(feature, float("inf"), float("inf"), True, "halt_and_request_review")
    edges = np.histogram_bin_edges(reference, bins=bins)
    if len(edges) < 3 or edges[0] == edges[-1]:
        edges = np.linspace(float(reference.min()) - 1.0, float(reference.max()) + 1.0, bins + 1)
    p, q = _histogram(reference, edges), _histogram(current, edges)
    psi = float(np.sum((q - p) * np.log(q / p)))
    midpoint = (p + q) / 2.0
    jsd = float(0.5 * np.sum(p * np.log(p / midpoint)) + 0.5 * np.sum(q * np.log(q / midpoint)))
    warning = psi >= psi_threshold or jsd >= jsd_threshold
    return DriftReport(feature, psi, jsd, warning, "feed_section20_weights_and_retirement_review" if warning else "monitor")
