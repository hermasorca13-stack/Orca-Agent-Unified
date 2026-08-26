"""Legal, tax-ledger, continuity, insurance and benchmark controls for Section 23."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal


@dataclass(frozen=True)
class LegalStatus:
    jurisdiction: str
    activity: str
    status: str
    source_checked_at: str
    counsel_required: bool
    allowed_to_trade: bool
    reason: str


class LegalComplianceGate:
    """Records facts and holds; it does not provide legal advice or infer a license."""

    def __init__(self, *, jurisdiction: str, activity: str):
        self.jurisdiction = jurisdiction
        self.activity = activity

    def assess(self, *, official_source_verified: bool, qualified_counsel_approved: bool, licence_reference: str = "") -> LegalStatus:
        allowed = bool(official_source_verified and qualified_counsel_approved and licence_reference.strip())
        status = "cleared_for_separate_legal_review" if allowed else "hard_compliance_hold"
        reason = "all external legal approvals recorded" if allowed else "no automated layer may treat market statistics as legal authorization"
        return LegalStatus(self.jurisdiction, self.activity, status, datetime.now(timezone.utc).isoformat(), True, allowed, reason)


@dataclass(frozen=True)
class MiCAStatus:
    counterparty: str
    register_checked: bool
    authorised: bool
    register_version: str
    allowed_to_trade: bool
    reason: str


def check_mica_counterparty(*, counterparty: str, register_checked: bool, authorised: bool, register_version: str) -> MiCAStatus:
    allowed = bool(register_checked and authorised and register_version.strip())
    return MiCAStatus(counterparty, register_checked, authorised, register_version, allowed, "authorisation_recorded" if allowed else "hold_until_authorisation_and_scope_verified")


@dataclass(frozen=True)
class TaxLedgerEntry:
    trade_id: str
    timestamp: str
    jurisdiction: str
    asset: str
    quantity: Decimal
    price: Decimal
    fee: Decimal
    side: str


class TaxLedger:
    def __init__(self, *, jurisdiction: str):
        self.jurisdiction = jurisdiction
        self.entries: list[TaxLedgerEntry] = []

    def record(self, *, trade_id: str, asset: str, quantity: Decimal, price: Decimal, fee: Decimal, side: str, timestamp: datetime | None = None) -> TaxLedgerEntry:
        if quantity <= 0 or price < 0 or fee < 0 or side not in {"buy", "sell"}:
            raise ValueError("invalid tax ledger entry")
        entry = TaxLedgerEntry(trade_id, (timestamp or datetime.now(timezone.utc)).isoformat(), self.jurisdiction, asset, quantity, price, fee, side)
        self.entries.append(entry)
        return entry


@dataclass(frozen=True)
class ContinuityControl:
    primary_operator: str
    alternate_operator: str
    alternate_can_trigger_kill_switch: bool
    custody_access_separated: bool
    accepted: bool


def validate_continuity(*, primary_operator: str, alternate_operator: str, alternate_can_trigger_kill_switch: bool, custody_access_separated: bool) -> ContinuityControl:
    accepted = bool(primary_operator.strip() and alternate_operator.strip() and alternate_operator != primary_operator and alternate_can_trigger_kill_switch and custody_access_separated)
    return ContinuityControl(primary_operator, alternate_operator, alternate_can_trigger_kill_switch, custody_access_separated, accepted)


@dataclass(frozen=True)
class InsuranceRecord:
    policy_reference: str
    covers_hot_assets: bool
    custody_and_crime_scope_verified: bool
    accepted: bool


def record_insurance(*, policy_reference: str, covers_hot_assets: bool, custody_and_crime_scope_verified: bool) -> InsuranceRecord:
    return InsuranceRecord(policy_reference, covers_hot_assets, custody_and_crime_scope_verified, bool(policy_reference.strip() and covers_hot_assets and custody_and_crime_scope_verified))


@dataclass(frozen=True)
class BenchmarkComparison:
    strategy_return: float
    benchmark_return: float
    excess_return: float
    benchmark_name: str


def compare_benchmark(strategy_return: float, benchmark_return: float, *, benchmark_name: str = "BTC_buy_and_hold") -> BenchmarkComparison:
    return BenchmarkComparison(float(strategy_return), float(benchmark_return), float(strategy_return - benchmark_return), benchmark_name)
