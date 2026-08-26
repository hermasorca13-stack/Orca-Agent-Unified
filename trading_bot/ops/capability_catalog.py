"""Evidence-backed capability catalog extracted from the supplied TypeScript file.

This is an audit/documentation index only. It has no trading authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CapabilityStatus = Literal["implemented", "configured", "documented", "tested", "guardrail", "blocked"]


@dataclass(frozen=True)
class Capability:
    id: str
    name: str
    status: CapabilityStatus
    description: str
    evidence: tuple[str, ...]
    tags: tuple[str, ...]


ORCA_CAPABILITIES: tuple[Capability, ...] = (
    Capability("catalog-evidence-contract", "سجل القدرات القائم على الدليل", "implemented", "فهرس ثابت يربط كل قدرة بحالتها وملفات إثباتها ووسومها لمنع التكرار والادعاء غير المدعوم.", ("trading_bot/ops/capability_catalog.py", "docs/CAPABILITY_CATALOG.md"), ("catalog", "evidence", "audit", "deduplication")),
    Capability("paper-safe-default", "Paper كافتراضي آمن", "guardrail", "الوضع الورقي هو الافتراضي ولا يملك الفهرس أو أي طبقة معرفية صلاحية إرسال أوامر.", ("trading_bot/config/settings.py", "trading_bot/execution/engine.py"), ("paper", "no-live", "guardrail")),
    Capability("local-secret-boundary", "حد الأسرار المحلي", "guardrail", "الأسرار لا تدخل الفهرس ولا السجل؛ تُقرأ فقط من خزنة نظام التشغيل عند الحاجة.", ("trading_bot/security/vault.py", "trading_bot/cli/local_setup.py"), ("secrets", "keyring", "least-privilege")),
    Capability("market-data-lineage", "سلسلة منشأ بيانات السوق", "implemented", "حفظ المصدر والزمن والبصمة وحالة التحقق قبل استخدام بيانات السوق.", ("trading_bot/analytics/data_quality23.py", "trading_bot/data/providers.py"), ("data-quality", "point-in-time", "sha256")),
    Capability("multilingual-event-context", "سياق الأحداث متعدد اللغات", "implemented", "أحداث وجلسات ومشاعر سياقية تدخل بوابة المخاطر ولا تتحول إلى أمر مستقل.", ("trading_bot/analytics/section24.py", "trading_bot/analytics/rss24.py"), ("events", "multilingual", "risk-only")),
    Capability("adaptive-risk-layers", "التحليل التكيفي المراجع", "tested", "القسمان 20–24 يقدمان مخرجات مراجعة وقيودًا أحادية الاتجاه مع Kill-Switch.", ("trading_bot/analytics/section20.py", "trading_bot/analytics/section21.py", "trading_bot/analytics/section22.py", "trading_bot/analytics/section23.py", "trading_bot/analytics/section24.py", "tests/trading_bot/test_engine.py"), ("adaptive", "review-only", "kill-switch")),
    Capability("defensive-import-fallback", "الاستيراد الدفاعي والرجوع الآمن", "implemented", "رفض البيانات غير الصالحة والرجوع إلى حالة موثقة بدل تحويل النقص إلى أداء أو إشارة.", ("trading_bot/ops/readiness.py", "trading_bot/storage/audit.py"), ("defensive", "fallback", "resilience")),
)


def validate_catalog(items: tuple[Capability, ...] = ORCA_CAPABILITIES) -> None:
    ids = [item.id for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate capability id")
    for item in items:
        if not item.evidence:
            raise ValueError(f"capability lacks evidence: {item.id}")
        if any(not tag.strip() for tag in item.tags):
            raise ValueError(f"blank capability tag: {item.id}")


def find_capabilities(query: str) -> tuple[Capability, ...]:
    normalized = query.strip().lower()
    if not normalized:
        return ORCA_CAPABILITIES
    return tuple(item for item in ORCA_CAPABILITIES if normalized in " ".join((item.id, item.name, item.description, *item.evidence, *item.tags)).lower())


def capabilities_by_status(status: CapabilityStatus) -> tuple[Capability, ...]:
    return tuple(item for item in ORCA_CAPABILITIES if item.status == status)


def capability_summary() -> dict[str, int]:
    validate_catalog()
    return {status: len(capabilities_by_status(status)) for status in ("implemented", "configured", "documented", "tested", "guardrail", "blocked")}
