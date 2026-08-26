"""Section 22 bounded continuous calibration with review-only Bayesian proposals."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from math import exp, sqrt

import numpy as np


@dataclass(frozen=True)
class SafeParameter:
    name: str
    lower: float
    upper: float
    default: float
    discrete_values: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if not self.lower <= self.default <= self.upper or self.lower >= self.upper:
            raise ValueError(f"invalid safe range for {self.name}")
        if self.discrete_values and any(not self.lower <= value <= self.upper for value in self.discrete_values):
            raise ValueError(f"discrete value outside safe range for {self.name}")


DEFAULT_SAFE_PARAMETERS = (
    SafeParameter("meta_probability", 0.50, 0.80, 0.55),
    SafeParameter("fractional_kelly", 0.01, 0.25, 0.10),
    SafeParameter("atr_profit_multiplier", 0.75, 3.00, 1.50),
    SafeParameter("atr_stop_multiplier", 0.50, 2.00, 1.00),
    SafeParameter("cpcv_embargo_bars", 1.0, 48.0, 3.0, (1.0, 3.0, 6.0, 12.0, 24.0, 48.0)),
    SafeParameter("shadow_days", 7.0, 90.0, 30.0, (7.0, 14.0, 30.0, 60.0, 90.0)),
    SafeParameter("signal_threshold", 0.10, 1.00, 0.50),
    SafeParameter("zscore_limit", 1.00, 5.00, 2.00),
)


@dataclass(frozen=True)
class CalibrationProposal:
    values: dict[str, float]
    posterior_probability: float
    context: str
    reason: str
    review_only: bool = True
    execution_eligible: bool = False


@dataclass(frozen=True)
class CalibrationResult:
    values: dict[str, float]
    score: float
    gates_passed: bool
    reason: str
    context: str = "unknown"


class BayesianCalibrator:
    """A small dependency-free GP-like surrogate and contextual Thompson sampler.

    This is an optimizer for proposals only. It cannot mutate risk policy or authorize orders.
    """

    def __init__(self, *, parameters: tuple[SafeParameter, ...] = DEFAULT_SAFE_PARAMETERS, seed: int = 22, cadence_days: int = 7, window_size: int = 64):
        self.parameters = parameters
        self._specs = {parameter.name: parameter for parameter in parameters}
        self.rng = np.random.default_rng(seed)
        self.cadence = timedelta(days=min(7, max(1, cadence_days)))
        self.observations: list[CalibrationResult] = []
        self.window_size = max(8, window_size)
        self._last_proposal: datetime | None = None
        self._quarterly_review = False

    def can_propose(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return self._last_proposal is None or now - self._last_proposal >= self.cadence

    def mark_quarterly_review(self, reviewer: str) -> None:
        if not reviewer.strip():
            raise ValueError("quarterly reviewer is required")
        self._quarterly_review = True

    def update_safe_range(self, name: str, lower: float, upper: float, *, reviewer: str) -> None:
        if not self._quarterly_review:
            raise PermissionError("safe ranges require a written quarterly review")
        if not reviewer.strip() or name not in self._specs or lower >= upper:
            raise ValueError("invalid reviewed safe range")
        old = self._specs[name]
        if not lower <= old.default <= upper:
            raise ValueError("reviewed range must retain current default")
        self._specs[name] = SafeParameter(name, lower, upper, old.default, old.discrete_values)
        self.parameters = tuple(self._specs[parameter.name] for parameter in self.parameters)
        self._quarterly_review = False

    def _vector(self, values: dict[str, float]) -> np.ndarray:
        return np.array([float(values.get(parameter.name, parameter.default)) for parameter in self.parameters], dtype=float)

    def _valid(self, values: dict[str, float]) -> bool:
        return all(parameter.lower <= values.get(parameter.name, parameter.default) <= parameter.upper for parameter in self.parameters)

    def _posterior(self, point: np.ndarray) -> tuple[float, float]:
        if not self.observations:
            return 0.0, 1.0
        recent = self.observations[-self.window_size:]
        X = np.array([self._vector(result.values) for result in recent])
        y = np.array([result.score for result in recent])
        scale = np.array([max(parameter.upper - parameter.lower, 1e-9) for parameter in self.parameters])
        X_scaled = X / scale
        point_scaled = point / scale
        if len(recent) >= 2:
            try:
                from sklearn.gaussian_process import GaussianProcessRegressor
                from sklearn.gaussian_process.kernels import Matern, WhiteKernel
                kernel = Matern(length_scale=1.0, nu=2.5) + WhiteKernel(noise_level=1e-3)
                model = GaussianProcessRegressor(kernel=kernel, normalize_y=True, random_state=22, n_restarts_optimizer=0)
                model.fit(X_scaled, y)
                mean, std = model.predict(point_scaled.reshape(1, -1), return_std=True)
                return float(mean[0]), float(max(std[0], 1e-6))
            except Exception:
                pass
        distances = np.sum((X_scaled - point_scaled) ** 2, axis=1)
        weights = np.exp(-distances / 0.20)
        if weights.sum() <= 1e-12:
            return float(y.mean()), 1.0
        mean = float(np.average(y, weights=weights))
        variance = float(np.average((y - mean) ** 2, weights=weights))
        uncertainty = sqrt(max(variance, 1e-6) + 1.0 / (1.0 + weights.sum()))
        return mean, uncertainty

    def propose(self, *, context: str = "unknown", now: datetime | None = None) -> CalibrationProposal | None:
        now = now or datetime.now(timezone.utc)
        if not self.can_propose(now):
            return None
        candidates: list[dict[str, float]] = []
        for _ in range(32):
            values = {}
            for parameter in self.parameters:
                if parameter.discrete_values:
                    values[parameter.name] = float(self.rng.choice(parameter.discrete_values))
                else:
                    values[parameter.name] = float(self.rng.uniform(parameter.lower, parameter.upper))
            candidates.append(values)
        scored = []
        for values in candidates:
            mean, uncertainty = self._posterior(self._vector(values))
            scored.append((mean + float(self.rng.normal(0.0, uncertainty)), values, mean, uncertainty))
        _, values, mean, uncertainty = max(scored, key=lambda item: item[0])
        self._last_proposal = now
        posterior_probability = float(1.0 / (1.0 + exp(-mean / max(uncertainty, 1e-9))))
        return CalibrationProposal(values, posterior_probability, context, "bounded_gp_surrogate_bandit_over_bandit_review_only")

    def record_result(self, proposal: CalibrationProposal, *, score: float, cpcv_pass: bool, pbo: float, dsr: float, shadow_pass: bool) -> CalibrationResult:
        gates_passed = bool(cpcv_pass and pbo <= 0.05 and dsr > 0.0 and shadow_pass)
        reason = "all_section20_gates_passed_review_required" if gates_passed else "section20_gate_failed"
        result = CalibrationResult(dict(proposal.values), float(score), gates_passed, reason, proposal.context)
        self.observations.append(result)
        return result

    def thompson_discrete(self, *, name: str, context: str = "unknown") -> float:
        parameter = self._specs.get(name)
        if parameter is None or not parameter.discrete_values:
            raise ValueError(f"{name} is not a registered discrete parameter")
        samples = []
        for value in parameter.discrete_values:
            contextual = [result for result in self.observations if result.context == context and result.values.get(name) == value and result.reason]
            matching = [result.score for result in contextual]
            if not matching:
                matching = [result.score for result in self.observations if result.values.get(name) == value and result.reason]
            alpha = 1.0 + sum(score > 0 for score in matching)
            beta = 1.0 + sum(score <= 0 for score in matching)
            samples.append((float(self.rng.beta(alpha, beta)), value))
        return float(max(samples)[1])
