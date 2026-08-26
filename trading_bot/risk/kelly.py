"""Conservative confidence and volatility-scaled position sizing."""
from __future__ import annotations


def fractional_kelly_probability(probability: float, payoff_ratio: float, *, fraction: float = 0.25, cap: float = 0.01) -> float:
    p = min(1.0, max(0.0, probability))
    b = max(0.0, payoff_ratio)
    if b <= 0:
        return 0.0
    q = 1.0 - p
    full_kelly = (b * p - q) / b
    return min(cap, max(0.0, fraction * full_kelly))


def confidence_volatility_size(*, equity: float, probability: float, payoff_ratio: float, atr_pct: float, risk_cap_pct: float = 0.01, kelly_fraction: float = 0.25) -> float:
    confidence_fraction = fractional_kelly_probability(probability, payoff_ratio, fraction=kelly_fraction, cap=risk_cap_pct)
    volatility_fraction = min(risk_cap_pct, risk_cap_pct / max(atr_pct, 1e-9))
    return equity * min(confidence_fraction, volatility_fraction, risk_cap_pct)
