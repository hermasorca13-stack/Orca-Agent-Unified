"""Canonical domain models for ORCA Max Mouny trading engine."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TradingMode(str, Enum):
    PAPER = "paper"
    SANDBOX = "sandbox"
    LIVE = "live"


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    LIMIT = "limit"
    MARKET = "market"
    STOP_LIMIT = "stop_limit"


@dataclass(frozen=True)
class MarketQuote:
    exchange: str
    symbol: str
    bid: float
    ask: float
    bid_size: float = 0.0
    ask_size: float = 0.0
    timestamp: datetime = field(default_factory=utc_now)
    funding_rate: float = 0.0
    open_interest: float = 0.0
    volume_24h: float = 0.0
    latency_ms: float = 0.0

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread_bps(self) -> float:
        return ((self.ask - self.bid) / self.mid * 10_000) if self.mid else float("inf")


@dataclass(frozen=True)
class OrderRequest:
    exchange: str
    symbol: str
    side: Side
    amount: float
    price: float | None = None
    order_type: OrderType = OrderType.LIMIT
    reduce_only: bool = False
    client_order_id: str = ""
    strategy: str = ""


@dataclass(frozen=True)
class Fill:
    order_id: str
    exchange: str
    symbol: str
    side: Side
    amount: float
    price: float
    fee: float
    fee_currency: str
    timestamp: datetime = field(default_factory=utc_now)
    status: str = "closed"


@dataclass
class Position:
    exchange: str
    symbol: str
    side: Side
    amount: float
    entry_price: float
    mark_price: float
    leverage: float = 1.0
    strategy: str = ""
    realized_pnl: float = 0.0

    @property
    def notional(self) -> float:
        return abs(self.amount * self.mark_price)

    @property
    def unrealized_pnl(self) -> float:
        direction = 1.0 if self.side == Side.BUY else -1.0
        return direction * (self.mark_price - self.entry_price) * self.amount


@dataclass(frozen=True)
class PairValidation:
    symbol_a: str
    symbol_b: str
    hedge_ratio: float
    spread_mean: float
    spread_std: float
    z_score: float
    cointegrated: bool
    stationary: bool
    correlation: float
    sample_size: int
    reason: str


@dataclass(frozen=True)
class Signal:
    strategy: str
    symbol: str
    side: Side
    score: float
    expected_edge_bps: float
    stop_price: float | None
    target_prices: tuple[float, ...]
    confidence: float
    reasons: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class CostEstimate:
    fees: float
    spread: float
    slippage: float
    funding: float
    borrow: float
    transfer: float
    gas: float

    @property
    def total(self) -> float:
        return sum((self.fees, self.spread, self.slippage, self.funding, self.borrow, self.transfer, self.gas))


@dataclass(frozen=True)
class RiskSnapshot:
    equity: float
    available_margin: float
    margin_used: float
    liquidation_buffer: float
    total_exposure: float
    beta_exposure: float
    daily_pnl: float
    monthly_pnl: float
    consecutive_losses: int
    data_age_seconds: float
    api_latency_ms: float
    spread_bps: float
    weekend: bool = False
    event_lock: bool = False
    withdrawals_enabled: bool = False


@dataclass(frozen=True)
class GateResult:
    allowed: bool
    code: str
    reasons: tuple[str, ...] = ()
    checked_at: datetime = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["checked_at"] = self.checked_at.isoformat()
        return result


def jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return {key: jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set)):
        return [jsonable(item) for item in value]
    return value
