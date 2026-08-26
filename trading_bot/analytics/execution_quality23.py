"""Order-book execution quality controls for Section 23."""
from __future__ import annotations

from dataclasses import dataclass
from math import exp

import numpy as np


@dataclass(frozen=True)
class ToxicityReport:
    vpin: float
    buckets: int
    toxic: bool
    action: str


def vpin(prices: list[float], volumes: list[float], *, bucket_volume: float | None = None) -> ToxicityReport:
    if len(prices) != len(volumes) or len(prices) < 10:
        raise ValueError("VPIN requires at least 10 aligned price/volume observations")
    price = np.asarray(prices, dtype=float)
    volume = np.maximum(0.0, np.asarray(volumes, dtype=float))
    if not np.isfinite(price).all() or volume.sum() <= 0:
        raise ValueError("invalid VPIN inputs")
    bucket_volume = bucket_volume or max(float(volume.sum() / 20.0), 1e-9)
    imbalances: list[float] = []
    total_volume: list[float] = []
    signed = np.sign(np.diff(np.r_[price[0], price])) * volume
    current_signed, current_volume = 0.0, 0.0
    for signed_volume, raw_volume in zip(signed, volume):
        current_signed += float(signed_volume)
        current_volume += float(raw_volume)
        if current_volume >= bucket_volume:
            imbalances.append(abs(current_signed))
            total_volume.append(current_volume)
            current_signed, current_volume = 0.0, 0.0
    if current_volume > 0:
        imbalances.append(abs(current_signed))
        total_volume.append(current_volume)
    value = float(np.mean(np.asarray(imbalances) / np.maximum(total_volume, 1e-12))) if imbalances else 0.0
    toxic = value >= 0.70
    return ToxicityReport(value, len(imbalances), toxic, "cancel_or_widen_market_making_quotes" if toxic else "normal_quote_control")


@dataclass(frozen=True)
class QuoteProtection:
    spread_multiplier: float
    quote_allowed: bool
    reason: str


def protect_market_making(report: ToxicityReport, *, toxic_threshold: float = 0.70) -> QuoteProtection:
    if report.vpin >= toxic_threshold:
        return QuoteProtection(2.0 + min(2.0, report.vpin), False, "toxic_flow_cancel_quotes")
    return QuoteProtection(1.0 + report.vpin, True, "quote_with_toxicity_adjustment")


@dataclass(frozen=True)
class ExecutionSlice:
    offset_seconds: float
    fraction: float


class AlmgrenChrissScheduler:
    def __init__(self, *, risk_aversion: float = 0.5, seed: int = 23):
        self.risk_aversion = max(0.0, risk_aversion)
        self.seed = seed

    def schedule(self, quantity: float, *, slices: int = 8, horizon_seconds: float = 300.0) -> tuple[ExecutionSlice, ...]:
        if quantity <= 0 or slices < 1 or horizon_seconds <= 0:
            raise ValueError("quantity, slices and horizon must be positive")
        rng = np.random.default_rng(self.seed)
        grid = np.linspace(0.0, 1.0, slices)
        weights = np.exp(-self.risk_aversion * grid)
        weights /= weights.sum()
        jitter = rng.uniform(-0.12, 0.12, slices)
        offsets = np.sort(np.clip((grid + jitter / max(slices, 1)) * horizon_seconds, 0.0, horizon_seconds))
        return tuple(ExecutionSlice(float(offset), float(weight)) for offset, weight in zip(offsets, weights))


@dataclass(frozen=True)
class VenueQuote:
    venue: str
    depth_notional: float
    fee_bps: float
    fill_probability: float
    latency_ms: float


class SmartOrderRouter:
    def choose(self, quotes: list[VenueQuote], *, required_notional: float) -> VenueQuote | None:
        viable = [quote for quote in quotes if quote.depth_notional >= required_notional and quote.fill_probability > 0.0]
        if not viable:
            return None
        return max(viable, key=lambda quote: (quote.fill_probability * quote.depth_notional) / (1.0 + quote.fee_bps) - quote.latency_ms * 0.001)


@dataclass(frozen=True)
class DefiExecutionGuard:
    private_rpc: bool
    slippage_bps: float
    mev_cost_bps: float
    allowed: bool
    reason: str


def validate_defi_execution(*, private_rpc: bool, slippage_bps: float, mev_cost_bps: float, max_slippage_bps: float = 30.0, max_mev_cost_bps: float = 15.0) -> DefiExecutionGuard:
    allowed = bool(private_rpc and 0.0 <= slippage_bps <= max_slippage_bps and 0.0 <= mev_cost_bps <= max_mev_cost_bps)
    reason = "private_channel_and_cost_limits_ok" if allowed else "reject_defi_transaction_private_rpc_or_cost_limit_failed"
    return DefiExecutionGuard(private_rpc, slippage_bps, mev_cost_bps, allowed, reason)
