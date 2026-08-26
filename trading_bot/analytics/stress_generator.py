"""Conservative generative stress scenarios; not a claim of TimeGAN or neural generation."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class StressScenario:
    name: str
    returns: tuple[float, ...]
    max_drawdown: float
    stop_tightening_required: bool


class StressGenerator:
    def __init__(self, *, seed: int = 21, block_size: int = 8):
        self.rng = np.random.default_rng(seed)
        self.block_size = max(1, block_size)

    @staticmethod
    def _max_drawdown(values: np.ndarray) -> float:
        equity = np.cumprod(1.0 + values)
        peaks = np.maximum.accumulate(equity)
        return float(np.max(1.0 - equity / np.maximum(peaks, 1e-12))) if len(equity) else 0.0

    def block_bootstrap(self, returns: list[float], *, length: int | None = None) -> np.ndarray:
        source = np.asarray(returns, dtype=float)
        source = source[np.isfinite(source)]
        if len(source) < self.block_size:
            raise ValueError("not enough returns for block bootstrap")
        length = length or len(source)
        blocks = [source[i:i + self.block_size] for i in range(len(source) - self.block_size + 1)]
        result: list[float] = []
        while len(result) < length:
            result.extend(blocks[int(self.rng.integers(0, len(blocks)))])
        return np.asarray(result[:length])

    def generate(self, returns: list[float], *, scenarios: int = 32, length: int | None = None) -> list[StressScenario]:
        base = np.asarray(returns, dtype=float)
        if len(base) < self.block_size:
            raise ValueError("not enough returns for stress generation")
        output: list[StressScenario] = []
        for index in range(scenarios):
            sampled = self.block_bootstrap(list(base), length=length)
            # Conservative adversarial overlay: retain empirical shape but deepen downside only.
            downside = sampled < 0
            shock = np.zeros_like(sampled)
            shock[downside] = np.minimum(sampled[downside] * 0.50, -0.002)
            stressed = sampled + shock
            drawdown = self._max_drawdown(stressed)
            output.append(StressScenario(f"block_bootstrap_adversarial_{index + 1}", tuple(map(float, stressed)), drawdown, bool(drawdown > self._max_drawdown(base))))
        return output

    def worst_case(self, returns: list[float], *, scenarios: int = 32) -> StressScenario:
        generated = self.generate(returns, scenarios=scenarios)
        return max(generated, key=lambda scenario: scenario.max_drawdown)
