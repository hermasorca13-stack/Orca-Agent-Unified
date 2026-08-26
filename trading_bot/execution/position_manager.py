"""Position lifecycle rules: laddered exits, breakeven and trailing stops."""
from __future__ import annotations

from dataclasses import dataclass

from trading_bot.models import Position, Side


@dataclass(frozen=True)
class ExitDecision:
    action: str
    amount: float
    stop_price: float | None
    reason: str


def fibonacci_targets(entry: float, stop: float, side: Side) -> tuple[float, float]:
    risk = abs(entry - stop)
    if side == Side.BUY:
        return entry + risk * 1.382, entry + risk * 1.618
    return entry - risk * 1.382, entry - risk * 1.618


def manage_position(position: Position, *, stop_price: float, current_price: float, atr_value: float, target_index: int = 0) -> ExitDecision:
    if position.amount == 0:
        return ExitDecision("none", 0.0, None, "flat")
    direction = 1.0 if position.side == Side.BUY else -1.0
    profit_pct = direction * (current_price - position.entry_price) / position.entry_price
    if profit_pct >= 0.015:
        return ExitDecision("move_stop_to_breakeven", 0.0, position.entry_price, "profit_1_5_percent")
    trailing = current_price - 2.0 * atr_value if position.side == Side.BUY else current_price + 2.0 * atr_value
    hit_stop = current_price <= stop_price if position.side == Side.BUY else current_price >= stop_price
    if hit_stop:
        return ExitDecision("exit_all", abs(position.amount), stop_price, "stop_triggered")
    return ExitDecision("trail", 0.0, trailing, "atr_trailing_stop")
