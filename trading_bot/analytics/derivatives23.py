"""Options Greeks and portfolio exposure guardrails for Section 23."""
from __future__ import annotations

from dataclasses import dataclass
from math import erf, exp, log, pi, sqrt


@dataclass(frozen=True)
class OptionPosition:
    symbol: str
    quantity: float
    spot: float
    strike: float
    time_to_expiry: float
    volatility: float
    rate: float
    option_type: str = "call"


@dataclass(frozen=True)
class Greeks:
    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float


def _norm_pdf(x: float) -> float:
    return exp(-0.5 * x * x) / sqrt(2.0 * pi)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def option_greeks(position: OptionPosition) -> Greeks:
    if min(position.spot, position.strike, position.time_to_expiry, position.volatility) <= 0:
        raise ValueError("spot, strike, expiry and volatility must be positive")
    sign = 1.0 if position.option_type.lower() == "call" else -1.0
    sqrt_t = sqrt(position.time_to_expiry)
    d1 = (log(position.spot / position.strike) + (position.rate + 0.5 * position.volatility**2) * position.time_to_expiry) / (position.volatility * sqrt_t)
    d2 = d1 - position.volatility * sqrt_t
    delta = sign * _norm_cdf(sign * d1)
    gamma = _norm_pdf(d1) / (position.spot * position.volatility * sqrt_t)
    vega = position.spot * _norm_pdf(d1) * sqrt_t
    theta = -(position.spot * _norm_pdf(d1) * position.volatility / (2.0 * sqrt_t)) - sign * position.rate * position.strike * exp(-position.rate * position.time_to_expiry) * _norm_cdf(sign * d2)
    rho = sign * position.strike * position.time_to_expiry * exp(-position.rate * position.time_to_expiry) * _norm_cdf(sign * d2)
    return Greeks(delta * position.quantity, gamma * abs(position.quantity), vega * position.quantity, theta * position.quantity, rho * position.quantity)


@dataclass(frozen=True)
class GreeksExposure:
    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float
    vega_limit: float
    gamma_hedge_required: bool
    accepted: bool
    reason: str


def portfolio_greeks(positions: list[OptionPosition], *, vega_limit: float, gamma_expiry_days: float = 7.0, gamma_move_threshold: float = 0.05, spot_move: float = 0.0) -> GreeksExposure:
    totals = [0.0] * 5
    for position in positions:
        values = option_greeks(position)
        for index, value in enumerate((values.delta, values.gamma, values.vega, values.theta, values.rho)):
            totals[index] += value
    gamma_hedge = any(position.time_to_expiry * 365.0 <= gamma_expiry_days for position in positions) or abs(spot_move) >= gamma_move_threshold
    accepted = abs(totals[2]) <= abs(vega_limit)
    reason = "ok" if accepted else "vega_limit_exceeded_reduce_or_reject"
    if gamma_hedge:
        reason = f"{reason};gamma_neutralization_required" if reason != "ok" else "gamma_neutralization_required"
    return GreeksExposure(*totals, vega_limit, gamma_hedge, accepted, reason)


@dataclass(frozen=True)
class VolatilitySurface:
    maturities: tuple[float, ...]
    strikes: tuple[float, ...]
    implied_vols: tuple[tuple[float, ...], ...]
    skew: float
    term_structure_slope: float


def summarize_vol_surface(maturities: list[float], strikes: list[float], implied_vols: list[list[float]]) -> VolatilitySurface:
    if len(maturities) < 2 or len(strikes) < 2 or len(implied_vols) != len(maturities):
        raise ValueError("volatility surface requires at least 2 maturities and strikes")
    matrix = [list(map(float, row)) for row in implied_vols]
    if any(len(row) != len(strikes) for row in matrix):
        raise ValueError("surface dimensions do not match")
    skew = float(sum(row[-1] - row[0] for row in matrix) / len(matrix))
    term_structure_slope = float((sum(matrix[-1]) / len(matrix[-1])) - (sum(matrix[0]) / len(matrix[0])))
    return VolatilitySurface(tuple(maturities), tuple(strikes), tuple(tuple(row) for row in matrix), skew, term_structure_slope)
