"""Fail-closed risk gates for every order decision."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from trading_bot.config.settings import Settings
from trading_bot.models import CostEstimate, GateResult, RiskSnapshot, Signal


@dataclass(frozen=True)
class MarketContext:
    fear_greed: float = 50.0
    btc_above_200w: bool = True
    major_event_lock: bool = False
    high_liquidity_session: bool = True
    weekend: bool = False
    fully_hedged: bool = True
    atr_pct: float = 0.02
    volume_24h_usd: float = 1_000_000_000.0


class RiskEngine:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._halt_reason: str | None = None

    @property
    def halted(self) -> bool:
        return self._halt_reason is not None

    def halt(self, reason: str) -> None:
        self._halt_reason = reason

    def resume(self) -> None:
        self._halt_reason = None

    def emergency_gate(self, snapshot: RiskSnapshot) -> GateResult:
        reasons: list[str] = []
        if self._halt_reason:
            reasons.append(f"halted:{self._halt_reason}")
        if snapshot.data_age_seconds > self.settings.max_data_age_seconds:
            reasons.append("data_age_exceeded")
        if snapshot.api_latency_ms > self.settings.max_latency_ms:
            reasons.append("api_latency_exceeded")
        if snapshot.liquidation_buffer < 2.0:
            reasons.append("margin_buffer_below_2x")
        if snapshot.withdrawals_enabled:
            reasons.append("withdrawal_permission_detected")
        if snapshot.daily_pnl <= -(snapshot.equity * self.settings.max_daily_loss_pct):
            reasons.append("daily_loss_limit")
        if snapshot.monthly_pnl <= -(snapshot.equity * self.settings.max_monthly_loss_pct):
            reasons.append("monthly_loss_limit")
        if snapshot.consecutive_losses >= 3:
            reasons.append("three_consecutive_losses")
        if reasons:
            return GateResult(False, "EMERGENCY_STOP", tuple(reasons))
        return GateResult(True, "OK")

    def trade_gate(self, signal: Signal, context: MarketContext, snapshot: RiskSnapshot, costs: CostEstimate) -> GateResult:
        emergency = self.emergency_gate(snapshot)
        if not emergency.allowed:
            return emergency
        reasons: list[str] = []
        if costs.total <= 0:
            reasons.append("cost_model_missing_or_zero")
        # Strategy signal generators provide expected edge net of their modeled costs.
        if signal.expected_edge_bps <= 0.0:
            reasons.append("edge_does_not_cover_costs")
        if not self.settings.fear_greed_min <= context.fear_greed <= self.settings.fear_greed_max:
            reasons.append("fear_greed_outside_20_80")
        if not context.btc_above_200w:
            reasons.append("btc_below_200_week_average")
        if context.major_event_lock:
            reasons.append("major_event_lock")
        if not context.high_liquidity_session:
            reasons.append("outside_liquid_session")
        if context.weekend and not context.fully_hedged:
            reasons.append("unhedged_weekend_position")
        if context.atr_pct > self.settings.max_atr_pct:
            reasons.append("atr_above_5_percent")
        if context.volume_24h_usd < self.settings.min_volume_24h_usd:
            reasons.append("volume_below_500m_usd")
        if signal.confidence < 0.5:
            reasons.append("fewer_than_three_confirmations")
        if reasons:
            return GateResult(False, "REJECT", tuple(reasons))
        return GateResult(True, "APPROVED")

    def position_size(self, equity: float, stop_distance: float, price: float, atr_pct: float, *, leverage: float = 1.0) -> float:
        if equity <= 0 or stop_distance <= 0 or price <= 0:
            return 0.0
        risk_budget = equity * self.settings.max_order_risk_pct
        volatility_scale = min(1.0, self.settings.max_atr_pct / max(atr_pct, 1e-9))
        notional = risk_budget / (stop_distance / price) * volatility_scale
        return max(0.0, notional / price * min(leverage, self.settings.directional_leverage_max if leverage <= 2.0 else leverage))
