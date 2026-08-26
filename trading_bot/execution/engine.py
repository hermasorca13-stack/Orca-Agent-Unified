"""Order orchestration: staged entries, paired hedges and laddered exits."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Iterable

from trading_bot.adapters.base import ExchangeAdapter
from trading_bot.models import Fill, OrderRequest, OrderType, Side, Signal
from trading_bot.storage.audit import AuditLog


@dataclass(frozen=True)
class ExecutionPlan:
    exchange: str
    symbol: str
    side: Side
    amount: float
    price: float
    slices: int = 4
    reduce_only: bool = False
    strategy: str = ""
    approved: bool = False


class ExecutionEngine:
    def __init__(self, adapters: dict[str, ExchangeAdapter], audit: AuditLog):
        self.adapters = adapters
        self.audit = audit

    def staged_entry(self, plan: ExecutionPlan) -> list[Fill]:
        if not plan.approved:
            self.audit.write("execution_rejected", {"exchange": plan.exchange, "symbol": plan.symbol, "reason": "execution_plan_not_approved"})
            raise PermissionError("execution plan requires explicit approval from prior risk and execution gates")
        adapter = self.adapters[plan.exchange]
        slices = max(1, plan.slices)
        amount = plan.amount / slices
        fills: list[Fill] = []
        for index in range(slices):
            request = OrderRequest(
                exchange=plan.exchange,
                symbol=plan.symbol,
                side=plan.side,
                amount=amount,
                price=plan.price,
                order_type=OrderType.LIMIT,
                reduce_only=plan.reduce_only,
                client_order_id=f"orca-{uuid.uuid4().hex[:16]}-{index}",
                strategy=plan.strategy,
            )
            started = time.perf_counter()
            fill = adapter.create_order(request)
            latency_ms = (time.perf_counter() - started) * 1000.0
            self.audit.write("order_fill", {"request": request, "fill": fill, "latency_ms": latency_ms})
            fills.append(fill)
        return fills

    def hedged_entry(self, first: ExecutionPlan, hedge: ExecutionPlan) -> tuple[list[Fill], list[Fill]]:
        if first.exchange not in self.adapters or hedge.exchange not in self.adapters:
            raise ValueError("both hedge legs require configured adapters")
        started = time.perf_counter()
        primary = self.staged_entry(first)
        hedge_fills = self.staged_entry(hedge)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        self.audit.write("hedge_execution", {"primary": first, "hedge": hedge, "elapsed_ms": elapsed_ms})
        return primary, hedge_fills

    def laddered_exit(self, plan: ExecutionPlan, targets: Iterable[float]) -> list[Fill]:
        targets = tuple(targets)
        if not targets:
            return []
        fills: list[Fill] = []
        for target in targets:
            leg = ExecutionPlan(plan.exchange, plan.symbol, Side.SELL if plan.side == Side.BUY else Side.BUY, plan.amount / len(targets), target, 1, True, plan.strategy, plan.approved)
            fills.extend(self.staged_entry(leg))
        return fills
