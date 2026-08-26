"""Bounded autonomous alpha discovery.

Candidates are expression trees over approved columns only. They are research
artifacts and can never receive execution authority from this module.
"""
from __future__ import annotations

from dataclasses import dataclass
import random

import numpy as np
import pandas as pd


APPROVED_COLUMNS = ("close", "volume", "return_1", "return_5", "volatility", "funding_rate", "spread_bps")
OPERATORS = ("add", "sub", "mul", "safe_div", "neg")


@dataclass(frozen=True)
class AlphaCandidate:
    expression: str
    fitness: float
    sharpe: float
    simplicity: float
    generation: int
    causal_validated: bool = False
    shadow_validated: bool = False

    @property
    def execution_eligible(self) -> bool:
        return self.causal_validated and self.shadow_validated


def _terminal(rng: random.Random) -> str:
    return rng.choice(APPROVED_COLUMNS + ("1.0", "-1.0", "0.5"))


def _expression(rng: random.Random, depth: int = 0, max_depth: int = 2) -> str:
    if depth >= max_depth or rng.random() < 0.35:
        return _terminal(rng)
    operator = rng.choice(OPERATORS)
    if operator == "neg":
        return f"neg({_expression(rng, depth + 1, max_depth)})"
    return f"{operator}({_expression(rng, depth + 1, max_depth)},{_expression(rng, depth + 1, max_depth)})"


def _eval(expression: str, frame: pd.DataFrame) -> pd.Series:
    def split_args(value: str) -> list[str]:
        args, depth, start = [], 0, 0
        for position, character in enumerate(value):
            if character == "(": depth += 1
            elif character == ")": depth -= 1
            elif character == "," and depth == 0:
                args.append(value[start:position]); start = position + 1
        args.append(value[start:])
        return args

    def parse(value: str) -> pd.Series | float:
        value = value.strip()
        if value in frame.columns and value in APPROVED_COLUMNS:
            return frame[value].astype(float)
        try:
            return float(value)
        except ValueError:
            pass
        name, rest = value.split("(", 1)
        args = split_args(rest[:-1]) if name != "neg" else [rest[:-1]]
        values = [parse(arg) for arg in args]
        if name == "add": return values[0] + values[1]
        if name == "sub": return values[0] - values[1]
        if name == "mul": return values[0] * values[1]
        if name == "safe_div": return values[0] / (values[1].abs() + 1e-9)
        if name == "neg": return -values[0]
        raise ValueError(f"unsupported operator: {name}")
    result = parse(expression)
    return pd.Series(result, index=frame.index, dtype=float) if not isinstance(result, pd.Series) else result.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def evaluate_candidate(expression: str, frame: pd.DataFrame, *, generation: int = 0) -> AlphaCandidate:
    values = _eval(expression, frame)
    future_return = frame["close"].pct_change().shift(-1)
    signal = np.sign(values).replace(0.0, np.nan).ffill().fillna(0.0)
    returns = (signal * future_return).dropna()
    sharpe = float(returns.mean() / returns.std(ddof=1) * np.sqrt(365 * 24)) if len(returns) > 1 and returns.std(ddof=1) else 0.0
    simplicity = 1.0 / max(1, expression.count("(") + expression.count(","))
    fitness = sharpe + 0.1 * simplicity
    return AlphaCandidate(expression, float(fitness), sharpe, simplicity, generation)


def evolve(frame: pd.DataFrame, *, generations: int = 5, population_size: int = 24, seed: int = 7) -> list[AlphaCandidate]:
    rng = random.Random(seed)
    population = [_expression(rng) for _ in range(population_size)]
    candidates: list[AlphaCandidate] = []
    for generation in range(generations):
        scored = [evaluate_candidate(expression, frame, generation=generation) for expression in population]
        candidates.extend(scored)
        elite = [item.expression for item in sorted(scored, key=lambda item: (item.fitness, item.simplicity), reverse=True)[: max(2, population_size // 5)]]
        population = elite[:]
        while len(population) < population_size:
            parent = rng.choice(elite)
            population.append(parent if rng.random() < 0.25 else _expression(rng))
    return sorted(candidates, key=lambda item: (item.fitness, item.simplicity), reverse=True)
