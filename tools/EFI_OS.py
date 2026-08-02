#!/usr/bin/env python3
"""
EFI-OS — Evidence-Driven Founder Intelligence Operating System
===============================================================

ملف واحد مستقل، بلا مفاتيح API وبلا حزم خارجية. يحوّل محتوىً عامًا أو مُصرّحًا
به إلى أدلة موثقة، تحليلات قابلة للمراجعة، قاعدة معرفة قابلة للبحث، قواعد تنفيذية،
Workflows، ووكلاء منسقين مع بوابات تحقق هندسي.

تشغيل سريع:
  python EFI_OS.py self-test
  python EFI_OS.py demo
  python EFI_OS.py ingest-file --subject founder-a --path interview.txt --type interview
  python EFI_OS.py analyze --subject founder-a
  python EFI_OS.py research --query "كيف اتخذ القرار؟"
  python EFI_OS.py serve --port 8080

حدود مقصودة:
* لا يُحاكي عقل أي شخص ولا يستنتج نواياه الخاصة؛ يحلل أدلة منشورة قابلة للاستشهاد.
* لا يتجاوز تسجيل الدخول أو شروط المواقع. إدخال الويب هو URL عام صريح فقط.
* التحليل اللغوي الأساسي محلي وقابل للتشغيل بلا نموذج خارجي. يمكن لاحقًا وصل نموذج
  محلي للتفريغ أو التضمين الدلالي من دون API keys، لكن ذلك ليس مطلوبًا لتشغيل الملف.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sqlite3
import subprocess
import tempfile
import threading
import unittest
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from html.parser import HTMLParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen
from urllib.parse import urljoin
from urllib import robotparser
from uuid import uuid4


APP_NAME = "EFI-OS"
APP_VERSION = "1.0.0"
DEFAULT_DATABASE = "efi_os.db"
MAX_TEXT_CHARS = 2_000_000


# ---------------------------------------------------------------------------
# Models and invariants
# ---------------------------------------------------------------------------


class SourceType(StrEnum):
    INTERVIEW = "interview"
    VIDEO = "video"
    PAPER = "paper"
    PATENT = "patent"
    ARTICLE = "article"
    SOCIAL_POST = "social_post"
    CONFERENCE_TALK = "conference_talk"
    GITHUB_REPOSITORY = "github_repository"
    RELEASE_NOTE = "release_note"


class AnalysisKind(StrEnum):
    DECISION_CRISIS = "decision_crisis"
    ENGINEERING_MANAGEMENT = "engineering_management"
    PRODUCT_METHOD = "product_method"
    CODE_METHOD = "code_method"
    TESTING_QUALITY = "testing_quality"
    RISK_MANAGEMENT = "risk_management"
    CYBERSECURITY = "cybersecurity"
    AUTOMATION = "automation"
    AI_METHOD = "ai_method"
    REPEATED_PRINCIPLES = "repeated_principles"
    ENGINEERING_RULES = "engineering_rules"
    FAILURE_RECOVERY = "failure_recovery"
    THINKING_PATTERN = "thinking_pattern"
    REASONING_PATTERN = "reasoning_pattern"
    PROBLEM_DECOMPOSITION = "problem_decomposition"
    HYPOTHESIS_REVIEW = "hypothesis_review"
    EVIDENCE_VALIDATION = "evidence_validation"
    DECISION_MAKING = "decision_making"
    PRIORITIZATION = "prioritization"
    TIME_MANAGEMENT = "time_management"
    RESOURCE_MANAGEMENT = "resource_management"
    COMMUNICATION = "communication"
    MEETING_MANAGEMENT = "meeting_management"
    CODE_REVIEW = "code_review"
    DESIGN_REVIEW = "design_review"
    RESEARCH_REVIEW = "research_review"
    EXPERIMENTATION = "experimentation"
    LEARNING = "learning"
    KNOWLEDGE_SOURCES = "knowledge_sources"
    BOOK_RECOMMENDATIONS = "book_recommendations"
    SCIENTIFIC_INFLUENCES = "scientific_influences"
    SCHOOLS_OF_THOUGHT = "schools_of_thought"
    PRODUCT_EVOLUTION = "product_evolution"
    COMPARISON = "comparison"


# مصفوفة تتبع المتطلبات: كل بند من النطاق الأصلي يقابله مكوّن تنفيذي في هذا الملف.
CAPABILITY_REGISTRY: dict[str, str] = {
    "01_audio_video_interviews": "LocalToolConnector.transcribe + SourceType.INTERVIEW/VIDEO",
    "02_scientific_papers": "LocalToolConnector.pdf_to_text + SourceType.PAPER",
    "03_patents": "LocalFileConnector + SourceType.PATENT",
    "04_technical_articles": "LocalFileConnector/PublicURLConnector/ApprovedDomainCrawler + SourceType.ARTICLE",
    "05_public_social_posts": "LocalFileConnector/PublicURLConnector + SourceType.SOCIAL_POST",
    "06_lectures_conferences": "LocalToolConnector + SourceType.CONFERENCE_TALK",
    "07_github_repositories": "LocalGitConnector",
    "08_product_versions": "SourceType.RELEASE_NOTE + AnalysisKind.PRODUCT_EVOLUTION",
    "09_17_engineering_methods": "AnalysisKind decision/management/product/code/testing/risk/security/automation/ai",
    "18_20_principles_rules_failures": "PatternSynthesizer + RuleCompiler + AnalysisKind.FAILURE_RECOVERY",
    "21_24_compare_common_difference_rank": "PatternSynthesizer.compare_subjects + ranked_principles",
    "25_28_rules_workflows_agents_os": "RuleCompiler + RuleEngine + DecisionWorkflow + ResearchOrchestrator",
    "29_searchable_rag": "LocalRAG + KnowledgeStore",
    "30_incremental_updates": "UpdateMonitor + source_watches",
    "deep_thinking_reasoning_learning": "AnalysisKind.THINKING_PATTERN through AnalysisKind.SCHOOLS_OF_THOUGHT",
    "final_artifacts": "ArtifactFactory knowledge_base/encyclopedia/decision_tree/prompt/checklist/playbook/pattern_catalog",
    "engineering_gates": "SOURCE_GATE/EVIDENCE_GATE/ANALYSIS_GATE/RULE_GATE/release_gate",
}


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def normalise_space(text: str) -> str:
    return " ".join(text.replace("\x00", " ").split())


def validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise ValueError("canonical_url must be a complete HTTP(S) URL")
    return url


def serialise(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, list):
        return [serialise(item) for item in value]
    if isinstance(value, tuple):
        return [serialise(item) for item in value]
    if isinstance(value, dict):
        return {str(key): serialise(item) for key, item in value.items()}
    return value


@dataclass(slots=True)
class Evidence:
    subject_id: str
    source_type: SourceType
    title: str
    canonical_url: str
    normalized_text: str
    source_excerpt: str
    original_language: str = "und"
    author_or_speaker: str | None = None
    published_at: str | None = None
    license_or_access_basis: str = "provided locally by the user"
    source_quality_score: float = 0.5
    provenance: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: new_id("ev"))
    retrieved_at: str = field(default_factory=now_iso)

    def __post_init__(self) -> None:
        self.canonical_url = validate_url(self.canonical_url)
        self.subject_id = self.subject_id.strip()
        self.title = self.title.strip()[:500]
        self.normalized_text = normalise_space(self.normalized_text)[:MAX_TEXT_CHARS]
        self.source_excerpt = normalise_space(self.source_excerpt)[:1000]
        if not self.subject_id:
            raise ValueError("subject_id is required")
        if not self.title:
            raise ValueError("title is required")
        if len(self.normalized_text) < 40:
            raise ValueError("normalized_text must contain at least 40 characters")
        if not 0 <= self.source_quality_score <= 1:
            raise ValueError("source_quality_score must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["source_type"] = self.source_type.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Evidence":
        copy = dict(data)
        copy["source_type"] = SourceType(copy["source_type"])
        return cls(**copy)


@dataclass(slots=True)
class Claim:
    subject_id: str
    kind: AnalysisKind
    statement: str
    evidence_ids: list[str]
    confidence: float
    limitations: list[str]
    counter_evidence_ids: list[str] = field(default_factory=list)
    status: str = "candidate"
    id: str = field(default_factory=lambda: new_id("claim"))
    created_at: str = field(default_factory=now_iso)

    def __post_init__(self) -> None:
        self.statement = normalise_space(self.statement)
        if not self.statement or not self.evidence_ids:
            raise ValueError("claims require a statement and at least one evidence ID")
        if not 0 <= self.confidence <= 1:
            raise ValueError("claim confidence must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["kind"] = self.kind.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Claim":
        copy = dict(data)
        copy["kind"] = AnalysisKind(copy["kind"])
        return cls(**copy)


@dataclass(slots=True)
class OperationalRule:
    name: str
    category: str
    trigger: str
    recommended_action: str
    rationale: str
    evidence_ids: list[str]
    confidence: float
    applicability: list[str]
    exclusions: list[str]
    counter_evidence_reviewed: bool
    version: str = "1.0.0"
    id: str = field(default_factory=lambda: new_id("rule"))
    created_at: str = field(default_factory=now_iso)

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.trigger.strip() or not self.recommended_action.strip():
            raise ValueError("rule name, trigger, and recommended action are required")
        if not self.evidence_ids:
            raise ValueError("an operational rule must cite evidence")
        if not 0 <= self.confidence <= 1:
            raise ValueError("rule confidence must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OperationalRule":
        return cls(**dict(data))


@dataclass(slots=True)
class GateResult:
    gate: str
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def require_passed(self) -> None:
        if not self.passed:
            raise ValueError(f"{self.gate} failed: {'; '.join(self.errors)}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SearchPlan:
    objective: str
    subject_names: list[str]
    languages: list[str]
    queries: list[str]
    exclusions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Citation:
    evidence_id: str
    title: str
    url: str
    excerpt: str
    score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RAGAnswer:
    answer: str
    citations: list[Citation]
    confidence: float
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {"answer": self.answer, "citations": serialise(self.citations), "confidence": self.confidence, "limitations": self.limitations}


@dataclass(slots=True)
class WorkflowResult:
    decision: str
    required_steps: list[str]
    release_allowed: bool
    reason: str
    gate_results: list[GateResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "required_steps": self.required_steps,
            "release_allowed": self.release_allowed,
            "reason": self.reason,
            "gate_results": serialise(self.gate_results),
        }


# ---------------------------------------------------------------------------
# Quality gates: engineering verification before each transition
# ---------------------------------------------------------------------------


Check = Callable[[dict[str, Any]], str | None]


class QualityGate:
    def __init__(self, name: str, checks: list[Check]) -> None:
        self.name = name
        self.checks = checks

    def evaluate(self, artifact: dict[str, Any]) -> GateResult:
        errors = [error for check in self.checks if (error := check(artifact))]
        return GateResult(self.name, not errors, errors)


def _check_url(artifact: dict[str, Any]) -> str | None:
    try:
        validate_url(str(artifact.get("canonical_url", "")))
    except ValueError:
        return "A canonical public-style HTTP(S) URL is required."
    return None


def _check_access_basis(artifact: dict[str, Any]) -> str | None:
    return None if str(artifact.get("license_or_access_basis", "")).strip() else "Access/licence basis is required."


def _check_text(artifact: dict[str, Any]) -> str | None:
    return None if len(str(artifact.get("normalized_text", "")).strip()) >= 40 else "At least 40 text characters are required."


def _check_provenance(artifact: dict[str, Any]) -> str | None:
    return None if artifact.get("provenance") else "Provenance metadata is required."


def _check_evidence_ids(artifact: dict[str, Any]) -> str | None:
    return None if artifact.get("evidence_ids") else "At least one evidence ID is required."


def _check_claim_limitations(artifact: dict[str, Any]) -> str | None:
    return None if artifact.get("limitations") else "Analytical limitations are required."


def _check_rule_confidence(artifact: dict[str, Any]) -> str | None:
    return None if float(artifact.get("confidence", 0)) >= 0.70 else "Rule confidence must be at least 0.70."


def _check_counter_review(artifact: dict[str, Any]) -> str | None:
    return None if artifact.get("counter_evidence_reviewed") else "Counter-evidence review is mandatory before rule approval."


SOURCE_GATE = QualityGate("source-gate", [_check_url, _check_access_basis])
EVIDENCE_GATE = QualityGate("evidence-gate", [_check_url, _check_access_basis, _check_text, _check_provenance])
ANALYSIS_GATE = QualityGate("analysis-gate", [_check_evidence_ids, _check_claim_limitations])
RULE_GATE = QualityGate("rule-gate", [_check_evidence_ids, _check_rule_confidence, _check_counter_review])


def release_gate(*, tests_passed: bool, security_reviewed: bool, privacy_reviewed: bool, rollback_ready: bool, observability_ready: bool) -> GateResult:
    values = {
        "Automated tests": tests_passed,
        "Security review": security_reviewed,
        "Privacy review": privacy_reviewed,
        "Rollback plan": rollback_ready,
        "Observability": observability_ready,
    }
    errors = [f"{name} is missing." for name, passed in values.items() if not passed]
    return GateResult("release-gate", not errors, errors)


# ---------------------------------------------------------------------------
# Local SQLite knowledge store (no remote database or key)
# ---------------------------------------------------------------------------


class KnowledgeStore:
    def __init__(self, database_path: str | Path = DEFAULT_DATABASE) -> None:
        self.path = str(database_path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    def _connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialise(self) -> None:
        connection = self._connection()
        try:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS evidence (
                  id TEXT PRIMARY KEY, subject_id TEXT NOT NULL, source_type TEXT NOT NULL,
                  title TEXT NOT NULL, canonical_url TEXT NOT NULL UNIQUE, payload TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_evidence_subject ON evidence(subject_id);
                CREATE TABLE IF NOT EXISTS claims (
                  id TEXT PRIMARY KEY, subject_id TEXT NOT NULL, kind TEXT NOT NULL,
                  payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_claims_subject ON claims(subject_id);
                CREATE TABLE IF NOT EXISTS rules (
                  id TEXT PRIMARY KEY, category TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, event TEXT NOT NULL, details TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS source_watches (
                  id TEXT PRIMARY KEY, subject_id TEXT NOT NULL, url TEXT NOT NULL, source_type TEXT NOT NULL,
                  language TEXT NOT NULL, access_basis TEXT NOT NULL, last_fingerprint TEXT, last_checked_at TEXT,
                  enabled INTEGER NOT NULL DEFAULT 1, payload TEXT NOT NULL
                );
                """
            )
            connection.commit()
        finally:
            connection.close()

    def _write(self, sql: str, values: tuple[Any, ...]) -> None:
        connection = self._connection()
        try:
            connection.execute(sql, values)
            connection.commit()
        finally:
            connection.close()

    def audit(self, event: str, details: dict[str, Any]) -> None:
        self._write("INSERT INTO audit_log(at,event,details) VALUES(?,?,?)", (now_iso(), event, json.dumps(serialise(details), ensure_ascii=False)))

    def save_evidence(self, evidence: Evidence) -> Evidence:
        EVIDENCE_GATE.evaluate(evidence.to_dict()).require_passed()
        self._write(
            "INSERT OR REPLACE INTO evidence(id,subject_id,source_type,title,canonical_url,payload,created_at) VALUES(?,?,?,?,?,?,?)",
            (evidence.id, evidence.subject_id, evidence.source_type.value, evidence.title, evidence.canonical_url, json.dumps(evidence.to_dict(), ensure_ascii=False), evidence.retrieved_at),
        )
        self.audit("evidence_saved", {"evidence_id": evidence.id, "subject_id": evidence.subject_id})
        return evidence

    def get_evidence(self, evidence_id: str) -> Evidence | None:
        connection = self._connection()
        try:
            row = connection.execute("SELECT payload FROM evidence WHERE id=?", (evidence_id,)).fetchone()
        finally:
            connection.close()
        return Evidence.from_dict(json.loads(row["payload"])) if row else None

    def list_evidence(self, subject_id: str | None = None) -> list[Evidence]:
        sql, values = "SELECT payload FROM evidence", ()
        if subject_id:
            sql += " WHERE subject_id=?"
            values = (subject_id,)
        sql += " ORDER BY created_at DESC"
        connection = self._connection()
        try:
            rows = connection.execute(sql, values).fetchall()
        finally:
            connection.close()
        return [Evidence.from_dict(json.loads(row["payload"])) for row in rows]

    def save_claims(self, claims: Iterable[Claim]) -> list[Claim]:
        collected = list(claims)
        if not collected:
            return []
        connection = self._connection()
        try:
            for claim in collected:
                ANALYSIS_GATE.evaluate(claim.to_dict()).require_passed()
                connection.execute(
                    "INSERT OR REPLACE INTO claims(id,subject_id,kind,payload,created_at) VALUES(?,?,?,?,?)",
                    (claim.id, claim.subject_id, claim.kind.value, json.dumps(claim.to_dict(), ensure_ascii=False), claim.created_at),
                )
            connection.commit()
        finally:
            connection.close()
        self.audit("claims_saved", {"claim_ids": [claim.id for claim in collected]})
        return collected

    def get_claim(self, claim_id: str) -> Claim | None:
        connection = self._connection()
        try:
            row = connection.execute("SELECT payload FROM claims WHERE id=?", (claim_id,)).fetchone()
        finally:
            connection.close()
        return Claim.from_dict(json.loads(row["payload"])) if row else None

    def list_claims(self, subject_id: str | None = None) -> list[Claim]:
        sql, values = "SELECT payload FROM claims", ()
        if subject_id:
            sql += " WHERE subject_id=?"
            values = (subject_id,)
        sql += " ORDER BY created_at DESC"
        connection = self._connection()
        try:
            rows = connection.execute(sql, values).fetchall()
        finally:
            connection.close()
        return [Claim.from_dict(json.loads(row["payload"])) for row in rows]

    def save_rule(self, rule: OperationalRule) -> OperationalRule:
        RULE_GATE.evaluate(rule.to_dict()).require_passed()
        self._write(
            "INSERT OR REPLACE INTO rules(id,category,payload,created_at) VALUES(?,?,?,?)",
            (rule.id, rule.category, json.dumps(rule.to_dict(), ensure_ascii=False), rule.created_at),
        )
        self.audit("rule_saved", {"rule_id": rule.id, "evidence_ids": rule.evidence_ids})
        return rule

    def list_rules(self) -> list[OperationalRule]:
        connection = self._connection()
        try:
            rows = connection.execute("SELECT payload FROM rules ORDER BY created_at DESC").fetchall()
        finally:
            connection.close()
        return [OperationalRule.from_dict(json.loads(row["payload"])) for row in rows]

    def stats(self) -> dict[str, int]:
        connection = self._connection()
        try:
            return {name: int(connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]) for name in ("evidence", "claims", "rules", "audit_log", "source_watches")}
        finally:
            connection.close()

    def save_watch(self, watch: dict[str, Any]) -> dict[str, Any]:
        required = ("subject_id", "url", "source_type", "language", "access_basis")
        missing = [name for name in required if not str(watch.get(name, "")).strip()]
        if missing:
            raise ValueError(f"Watch is missing required fields: {', '.join(missing)}")
        validate_url(str(watch["url"]))
        record = dict(watch)
        record.setdefault("id", new_id("watch"))
        record.setdefault("enabled", True)
        record.setdefault("last_fingerprint", None)
        record.setdefault("last_checked_at", None)
        self._write(
            """INSERT OR REPLACE INTO source_watches
               (id,subject_id,url,source_type,language,access_basis,last_fingerprint,last_checked_at,enabled,payload)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (record["id"], record["subject_id"], record["url"], record["source_type"], record["language"], record["access_basis"],
             record["last_fingerprint"], record["last_checked_at"], int(bool(record["enabled"])), json.dumps(record, ensure_ascii=False)),
        )
        self.audit("source_watch_saved", {"watch_id": record["id"], "url": record["url"]})
        return record

    def list_watches(self, enabled_only: bool = True) -> list[dict[str, Any]]:
        sql = "SELECT payload FROM source_watches" + (" WHERE enabled=1" if enabled_only else "")
        connection = self._connection()
        try:
            rows = connection.execute(sql).fetchall()
        finally:
            connection.close()
        return [json.loads(row["payload"]) for row in rows]


# ---------------------------------------------------------------------------
# Ingestion connectors: local-first, authorised public web optional
# ---------------------------------------------------------------------------


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._blocked = 0
        self._in_title = False
        self.title = ""
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._blocked += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._blocked:
            self._blocked -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        text = normalise_space(data)
        if not text or self._blocked:
            return
        self.parts.append(text)
        if self._in_title:
            self.title = f"{self.title} {text}".strip()

    @property
    def text(self) -> str:
        return normalise_space(" ".join(self.parts))


class _HTMLPage(_HTMLText):
    """HTML parser that keeps only ordinary hyperlinks for authorised domain crawling."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        super().handle_starttag(tag, attrs)
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)


class LocalFileConnector:
    """Imports a user-provided text, markdown, HTML, JSON, or locally extracted PDF text file."""

    SUPPORTED = {".txt", ".md", ".html", ".htm", ".json"}

    def ingest(self, *, subject_id: str, path: str | Path, source_type: SourceType, language: str = "und", quality: float = 0.70, access_basis: str = "provided locally by the user") -> Evidence:
        source = Path(path).resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Source file not found: {source}")
        suffix = source.suffix.casefold()
        if suffix not in self.SUPPORTED:
            raise ValueError(f"Unsupported source {suffix}. Convert PDF/audio/video to text locally first, or use LocalToolConnector.")
        raw = source.read_text(encoding="utf-8", errors="replace")
        title, text = source.stem, raw
        if suffix in {".html", ".htm"}:
            parser = _HTMLText()
            parser.feed(raw)
            title, text = parser.title or source.stem, parser.text
        elif suffix == ".json":
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                title = str(parsed.get("title", source.stem))
                text = str(parsed.get("text", parsed.get("content", raw)))
        return Evidence(
            subject_id=subject_id,
            source_type=source_type,
            title=title,
            canonical_url=f"https://local.efi-os.invalid/{quote(source.name)}",
            normalized_text=text,
            source_excerpt=normalise_space(text)[:500],
            original_language=language,
            license_or_access_basis=access_basis,
            source_quality_score=quality,
            provenance={"connector": "LocalFileConnector", "filename": source.name, "sha_note": "source supplied locally"},
        )


class LocalToolConnector:
    """Uses optional locally installed tools (pdftotext, a transcriber) without API keys or shells."""

    @staticmethod
    def pdf_to_text(pdf_path: str | Path, output_txt: str | Path, executable: str = "pdftotext") -> Path:
        pdf, target = Path(pdf_path).resolve(), Path(output_txt).resolve()
        if not pdf.is_file() or pdf.suffix.casefold() != ".pdf":
            raise ValueError("pdf_path must point to a local PDF")
        target.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run([executable, str(pdf), str(target)], capture_output=True, text=True, check=False, timeout=120)
        if completed.returncode != 0 or not target.exists():
            raise RuntimeError(f"Local PDF extraction failed: {completed.stderr.strip() or 'pdftotext unavailable'}")
        return target

    @staticmethod
    def transcribe(media_path: str | Path, output_txt: str | Path, command: list[str]) -> Path:
        """Run an explicitly configured local transcription command; no shell, no secret, no network."""
        media, target = Path(media_path).resolve(), Path(output_txt).resolve()
        if not media.is_file() or not command:
            raise ValueError("A local media file and an explicit local command are required")
        target.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run([*command, str(media), str(target)], capture_output=True, text=True, check=False, timeout=1800)
        if completed.returncode != 0 or not target.exists():
            raise RuntimeError(f"Local transcription failed: {completed.stderr.strip() or 'unknown error'}")
        return target


@dataclass(slots=True)
class WebPolicy:
    allowed_domains: set[str] = field(default_factory=set)
    max_download_bytes: int = 2_000_000
    user_agent: str = "EFI-OS/1.0 authorised research connector"

    def allows(self, url: str) -> bool:
        host = urlparse(url).hostname or ""
        return not self.allowed_domains or host in self.allowed_domains or any(host.endswith(f".{domain}") for domain in self.allowed_domains)


class PublicURLConnector:
    """Retrieves one explicit public URL. It never searches behind authentication or bypasses controls."""

    def __init__(self, policy: WebPolicy | None = None) -> None:
        self.policy = policy or WebPolicy()

    def ingest(self, *, subject_id: str, url: str, source_type: SourceType = SourceType.ARTICLE, language: str = "und", quality: float = 0.60, access_basis: str = "public page permitted by source terms") -> Evidence:
        validate_url(url)
        if not self.policy.allows(url):
            raise PermissionError("URL domain is outside the approved policy")
        request = Request(url, headers={"User-Agent": self.policy.user_agent})
        with urlopen(request, timeout=20) as response:  # explicit public URL only
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "text/plain"}:
                raise ValueError(f"Unsupported content type: {content_type}")
            raw = response.read(self.policy.max_download_bytes + 1)
            if len(raw) > self.policy.max_download_bytes:
                raise ValueError("Response exceeds policy byte limit")
            text = raw.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
        title = url
        if content_type == "text/html":
            parser = _HTMLText()
            parser.feed(text)
            title, text = parser.title or url, parser.text
        return Evidence(
            subject_id=subject_id,
            source_type=source_type,
            title=title,
            canonical_url=url,
            normalized_text=text,
            source_excerpt=text[:500],
            original_language=language,
            license_or_access_basis=access_basis,
            source_quality_score=quality,
            provenance={"connector": "PublicURLConnector", "content_type": content_type, "explicit_url": True},
        )


class ApprovedDomainCrawler:
    """Small, keyless crawler for explicitly authorised domains; honours robots.txt and page limits."""

    def __init__(self, policy: WebPolicy | None = None, max_pages: int = 20) -> None:
        self.policy = policy or WebPolicy()
        self.max_pages = max(1, min(max_pages, 200))

    def _robots_allow(self, url: str) -> bool:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rules = robotparser.RobotFileParser()
        rules.set_url(robots_url)
        try:
            rules.read()
            return rules.can_fetch(self.policy.user_agent, url)
        except Exception:
            # A crawler must fail closed when it cannot validate crawl policy.
            return False

    def _fetch_page(self, url: str) -> tuple[str, str, list[str]]:
        request = Request(url, headers={"User-Agent": self.policy.user_agent})
        with urlopen(request, timeout=20) as response:
            if response.headers.get_content_type() != "text/html":
                raise ValueError("Crawler accepts HTML pages only")
            raw = response.read(self.policy.max_download_bytes + 1)
            if len(raw) > self.policy.max_download_bytes:
                raise ValueError("Crawler response exceeds policy byte limit")
            page = raw.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
        parser = _HTMLPage()
        parser.feed(page)
        return parser.title or url, parser.text, parser.links

    def crawl(self, *, subject_id: str, seed_urls: list[str], source_type: SourceType = SourceType.ARTICLE, language: str = "und", query: str = "", access_basis: str = "public pages permitted by source terms") -> list[Evidence]:
        if not seed_urls:
            raise ValueError("At least one explicit seed URL is required")
        queue = list(dict.fromkeys(seed_urls))
        visited: set[str] = set()
        evidence: list[Evidence] = []
        while queue and len(evidence) < self.max_pages:
            url = queue.pop(0)
            if url in visited or not self.policy.allows(url) or not self._robots_allow(url):
                continue
            visited.add(url)
            try:
                title, text, links = self._fetch_page(url)
            except (OSError, ValueError):
                continue
            if len(text) >= 40:
                evidence.append(Evidence(
                    subject_id=subject_id, source_type=source_type, title=title, canonical_url=url,
                    normalized_text=text, source_excerpt=text[:500], original_language=language,
                    license_or_access_basis=access_basis, source_quality_score=0.60,
                    provenance={"connector": "ApprovedDomainCrawler", "seed_urls": seed_urls, "robots_checked": True},
                ))
            for href in links:
                candidate = urljoin(url, href).split("#", 1)[0]
                parsed = urlparse(candidate)
                if parsed.scheme in {"http", "https"} and self.policy.allows(candidate) and candidate not in visited and candidate not in queue:
                    queue.append(candidate)
        if query and evidence:
            # Rank crawl results locally using the same transparent retrieval logic as RAG.
            order = [citation.evidence_id for citation in LocalRAG(evidence).retrieve(query, limit=len(evidence))]
            by_id = {item.id: item for item in evidence}
            ranked_ids = set(order)
            evidence = [by_id[item_id] for item_id in order] + [item for item in evidence if item.id not in ranked_ids]
        return evidence


class LocalGitConnector:
    """Analyses a local or explicitly exported Git repository; it does not access private remote repositories."""

    EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".java", ".go", ".rs", ".cs", ".cpp", ".c", ".md", ".yml", ".yaml", ".json"}

    def ingest(self, *, subject_id: str, repository: str | Path, language: str = "und", quality: float = 0.80) -> Evidence:
        root = Path(repository).resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"Repository folder not found: {root}")
        fragments: list[str] = []
        for file in root.rglob("*"):
            if ".git" in file.parts or not file.is_file() or file.suffix.casefold() not in self.EXTENSIONS:
                continue
            try:
                body = file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            fragments.append(f"\n--- FILE: {file.relative_to(root)} ---\n{body[:20_000]}")
            if sum(len(item) for item in fragments) > MAX_TEXT_CHARS:
                break
        git_history = ""
        try:
            run = subprocess.run(["git", "-C", str(root), "log", "--pretty=format:%h %ad %s", "--date=short", "-n", "200"], capture_output=True, text=True, check=False, timeout=30)
            if run.returncode == 0:
                git_history = f"\n--- GIT HISTORY ---\n{run.stdout}"
        except OSError:
            pass
        text = normalise_space("".join(fragments) + git_history)
        if len(text) < 40:
            raise ValueError("No readable supported source files were found in repository")
        return Evidence(
            subject_id=subject_id,
            source_type=SourceType.GITHUB_REPOSITORY,
            title=root.name,
            canonical_url=f"https://local.efi-os.invalid/repository/{quote(root.name)}",
            normalized_text=text,
            source_excerpt=text[:500],
            original_language=language,
            license_or_access_basis="repository supplied locally by the user",
            source_quality_score=quality,
            provenance={"connector": "LocalGitConnector", "repository": root.name, "local_export": True},
        )


# ---------------------------------------------------------------------------
# Advanced research planning: multilingual query expansion and ranking fusion
# ---------------------------------------------------------------------------


class QueryPlanner:
    def build(self, *, objective: str, names: list[str], languages: list[str], topic_terms: list[str], aliases: dict[str, list[str]] | None = None) -> SearchPlan:
        aliases = aliases or {}
        variants = list(dict.fromkeys(alias for name in names for alias in [name, *aliases.get(name, [])] if alias.strip()))
        queries: list[str] = []
        for name in variants:
            for term in topic_terms:
                queries.extend([
                    f'"{name}" "{term}"',
                    f'"{name}" {term} interview OR talk OR article',
                    f'"{name}" {term} site:github.com OR site:arxiv.org OR site:patents.google.com',
                ])
        return SearchPlan(
            objective=objective,
            subject_names=variants,
            languages=list(dict.fromkeys(languages or ["und"])),
            queries=list(dict.fromkeys(queries)),
            exclusions=["private data", "credential-gated material", "unverifiable reposts", "copyright-infringing copies"],
        )


def reciprocal_rank_fusion(result_lists: dict[str, list[str]], constant: int = 60) -> list[dict[str, Any]]:
    """Combine independent ranked lists while preserving which sources produced each result."""
    scores: dict[str, float] = defaultdict(float)
    origins: dict[str, list[str]] = defaultdict(list)
    for source, documents in result_lists.items():
        for rank, document in enumerate(documents, start=1):
            scores[document] += 1 / (constant + rank)
            origins[document].append(source)
    return [
        {"document_id": document, "score": round(score, 6), "ranked_by": origins[document]}
        for document, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)
    ]


# ---------------------------------------------------------------------------
# Evidence extraction, specialised analytic lenses, critic, and comparison
# ---------------------------------------------------------------------------


ANALYSIS_PATTERNS: dict[AnalysisKind, tuple[str, ...]] = {
    AnalysisKind.DECISION_CRISIS: ("crisis", "incident", "emergency", "أزمة", "حادث", "طوارئ"),
    AnalysisKind.ENGINEERING_MANAGEMENT: ("team", "engineering team", "manager", "فريق", "إدارة", "مهندسين"),
    AnalysisKind.PRODUCT_METHOD: ("product", "customer", "launch", "roadmap", "منتج", "عميل", "إطلاق"),
    AnalysisKind.CODE_METHOD: ("code", "refactor", "implementation", "كود", "برمجة", "إعادة هيكلة"),
    AnalysisKind.TESTING_QUALITY: ("test", "quality", "verification", "testing", "اختبار", "جودة", "تحقق"),
    AnalysisKind.RISK_MANAGEMENT: ("risk", "mitigation", "rollback", "خطر", "مخاطر", "تخفيف", "تراجع"),
    AnalysisKind.CYBERSECURITY: ("security", "threat", "vulnerability", "أمن", "تهديد", "ثغرة"),
    AnalysisKind.AUTOMATION: ("automation", "pipeline", "ci", "cd", "أتمتة", "خط أنابيب"),
    AnalysisKind.AI_METHOD: ("artificial intelligence", "machine learning", "model", "ذكاء اصطناعي", "تعلم آلي", "نموذج"),
    AnalysisKind.REPEATED_PRINCIPLES: ("principle", "always", "never", "مبدأ", "دائما", "أبدا"),
    AnalysisKind.ENGINEERING_RULES: ("must", "should", "rule", "required", "يجب", "قاعدة", "يلزم"),
    AnalysisKind.FAILURE_RECOVERY: ("failure", "mistake", "postmortem", "learned", "فشل", "خطأ", "درس"),
    AnalysisKind.THINKING_PATTERN: ("think", "mental model", "first principles", "أفكر", "نموذج ذهني", "مبادئ أولى"),
    AnalysisKind.REASONING_PATTERN: ("because", "therefore", "evidence", "reason", "لأن", "لذلك", "دليل", "استدلال"),
    AnalysisKind.PROBLEM_DECOMPOSITION: ("break down", "decompose", "smaller", "تقسيم", "جزء", "تفكيك"),
    AnalysisKind.HYPOTHESIS_REVIEW: ("hypothesis", "assumption", "validate", "فرضية", "افتراض", "تحقق"),
    AnalysisKind.EVIDENCE_VALIDATION: ("data", "measure", "proof", "experiment", "بيانات", "قياس", "برهان", "تجربة"),
    AnalysisKind.DECISION_MAKING: ("decide", "decision", "trade-off", "choose", "قرار", "نختار", "مفاضلة"),
    AnalysisKind.PRIORITIZATION: ("priority", "impact", "urgent", "prioritize", "أولوية", "أثر", "عاجل"),
    AnalysisKind.TIME_MANAGEMENT: ("time", "deadline", "schedule", "وقت", "موعد", "جدول"),
    AnalysisKind.RESOURCE_MANAGEMENT: ("budget", "resource", "cost", "capacity", "ميزانية", "موارد", "تكلفة"),
    AnalysisKind.COMMUNICATION: ("communicate", "write", "explain", "تواصل", "نكتب", "شرح"),
    AnalysisKind.MEETING_MANAGEMENT: ("meeting", "agenda", "decision record", "اجتماع", "أجندة", "محضر"),
    AnalysisKind.CODE_REVIEW: ("pull request", "code review", "reviewer", "مراجعة كود", "طلب سحب"),
    AnalysisKind.DESIGN_REVIEW: ("design review", "architecture review", "مراجعة تصميم", "مراجعة معمارية"),
    AnalysisKind.RESEARCH_REVIEW: ("paper", "peer review", "literature", "ورقة", "مراجعة بحث", "أدبيات"),
    AnalysisKind.EXPERIMENTATION: ("experiment", "a/b", "prototype", "pilot", "تجربة", "نموذج أولي"),
    AnalysisKind.LEARNING: ("learn", "learning", "study", "تعلم", "دراسة"),
    AnalysisKind.KNOWLEDGE_SOURCES: ("source", "reference", "citation", "مصدر", "مرجع", "اقتباس"),
    AnalysisKind.BOOK_RECOMMENDATIONS: ("book", "read", "كتاب", "قراءة"),
    AnalysisKind.SCIENTIFIC_INFLUENCES: ("scientist", "influenced", "researcher", "عالم", "تأثر", "باحث"),
    AnalysisKind.SCHOOLS_OF_THOUGHT: ("philosophy", "school of thought", "paradigm", "فلسفة", "مدرسة فكرية", "منهج"),
    AnalysisKind.PRODUCT_EVOLUTION: ("release", "version", "changelog", "إصدار", "نسخة", "سجل التغييرات"),
}


def _sentences(text: str) -> list[str]:
    return [normalise_space(sentence) for sentence in re.split(r"(?<=[.!?؟])\s+|\n+", text) if len(normalise_space(sentence)) >= 45]


class EvidenceAnalyzer:
    """Local, explainable heuristic extractor. All claims retain evidence and limitations."""

    def analyze(self, evidence: Evidence, requested: list[AnalysisKind] | None = None) -> list[Claim]:
        wanted = requested or list(ANALYSIS_PATTERNS)
        claims: list[Claim] = []
        base_confidence = min(0.86, round(0.42 + evidence.source_quality_score * 0.42, 2))
        for sentence in _sentences(evidence.normalized_text):
            lower = sentence.casefold()
            for kind in wanted:
                terms = ANALYSIS_PATTERNS.get(kind, ())
                if any(term.casefold() in lower for term in terms):
                    claims.append(
                        Claim(
                            subject_id=evidence.subject_id,
                            kind=kind,
                            statement=sentence,
                            evidence_ids=[evidence.id],
                            confidence=base_confidence,
                            limitations=[
                                "This is an observable published statement, not a claim about private thought or intent.",
                                "Requires cross-source and counter-evidence review before promotion to a rule.",
                            ],
                        )
                    )
        return self._deduplicate(claims)

    @staticmethod
    def _deduplicate(claims: list[Claim]) -> list[Claim]:
        kept: list[Claim] = []
        fingerprints: set[tuple[str, str]] = set()
        for claim in claims:
            key = (claim.kind.value, claim.statement.casefold())
            if key not in fingerprints:
                fingerprints.add(key)
                kept.append(claim)
        return kept


class CriticAgent:
    """Finds possible disagreements; it flags review work and never falsely declares contradiction."""

    NEGATIONS = {"not", "never", "avoid", "no", "لا", "ليس", "لم", "لن", "تجنب"}

    def find_possible_conflicts(self, claims: list[Claim]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for index, left in enumerate(claims):
            left_words = set(re.findall(r"\w+", left.statement.casefold(), flags=re.UNICODE))
            for right in claims[index + 1 :]:
                if left.kind != right.kind:
                    continue
                right_words = set(re.findall(r"\w+", right.statement.casefold(), flags=re.UNICODE))
                overlap = left_words & right_words
                polarity_differs = bool(left_words & self.NEGATIONS) != bool(right_words & self.NEGATIONS)
                if len(overlap) >= 3 and polarity_differs:
                    result.append({"left_claim_id": left.id, "right_claim_id": right.id, "shared_terms": sorted(overlap), "status": "possible_conflict_needs_human_review"})
        return result


class PatternSynthesizer:
    """Builds evidence-backed recurring patterns and cross-subject comparisons."""

    def recurring_patterns(self, claims: list[Claim], min_sources: int = 2) -> list[dict[str, Any]]:
        grouped: dict[AnalysisKind, list[Claim]] = defaultdict(list)
        for claim in claims:
            grouped[claim.kind].append(claim)
        results: list[dict[str, Any]] = []
        for kind, members in grouped.items():
            evidence_ids = sorted({evidence_id for member in members for evidence_id in member.evidence_ids})
            if len(evidence_ids) < min_sources:
                continue
            results.append({
                "kind": kind.value,
                "statement": f"Recurring observable pattern in {kind.value} across {len(evidence_ids)} independent evidence items.",
                "evidence_ids": evidence_ids,
                "claim_ids": [member.id for member in members],
                "confidence": round(min(0.93, sum(member.confidence for member in members) / len(members) + 0.08), 2),
                "limitations": ["Similarity is topic-based and requires a reviewer to verify semantic equivalence."],
            })
        return results

    def ranked_principles(self, claims: list[Claim]) -> list[dict[str, Any]]:
        """Rank observable analytical categories by their evidence-backed frequency."""
        grouped: dict[AnalysisKind, list[Claim]] = defaultdict(list)
        for claim in claims:
            if claim.kind in {AnalysisKind.REPEATED_PRINCIPLES, AnalysisKind.ENGINEERING_RULES, AnalysisKind.DECISION_MAKING, AnalysisKind.HYPOTHESIS_REVIEW, AnalysisKind.EXPERIMENTATION}:
                grouped[claim.kind].append(claim)
        rankings = [
            {
                "rank": 0,
                "kind": kind.value,
                "frequency": len(members),
                "evidence_ids": sorted({identifier for member in members for identifier in member.evidence_ids}),
                "mean_confidence": round(sum(member.confidence for member in members) / len(members), 2),
            }
            for kind, members in grouped.items()
        ]
        rankings.sort(key=lambda item: (item["frequency"], item["mean_confidence"]), reverse=True)
        for rank, item in enumerate(rankings, start=1):
            item["rank"] = rank
        return rankings

    def compare_subjects(self, left_subject: str, right_subject: str, claims: list[Claim]) -> dict[str, Any]:
        left = {claim.kind for claim in claims if claim.subject_id == left_subject}
        right = {claim.kind for claim in claims if claim.subject_id == right_subject}
        return {
            "left_subject": left_subject,
            "right_subject": right_subject,
            "common_analytical_categories": sorted(kind.value for kind in left & right),
            "left_only_categories": sorted(kind.value for kind in left - right),
            "right_only_categories": sorted(kind.value for kind in right - left),
            "limitations": ["This compares documented analytical coverage, not inherent personality or capability."],
        }


# ---------------------------------------------------------------------------
# Local RAG: unicode lexical retrieval + quality weighting + citations
# ---------------------------------------------------------------------------


def _tokens(text: str) -> list[str]:
    return re.findall(r"[\w-]+", text.casefold(), flags=re.UNICODE)


class LocalRAG:
    """Dependency-free retrieval baseline. Replace with local multilingual embeddings only when needed."""

    def __init__(self, evidence: list[Evidence]) -> None:
        self.evidence = evidence
        self.documents = {item.id: Counter(_tokens(item.normalized_text)) for item in evidence}
        self.df: Counter[str] = Counter()
        for counts in self.documents.values():
            self.df.update(counts.keys())

    def retrieve(self, query: str, limit: int = 8) -> list[Citation]:
        query_terms = Counter(_tokens(query))
        if not query_terms:
            return []
        total = max(1, len(self.documents))
        scored: list[tuple[Evidence, float]] = []
        for item in self.evidence:
            terms = self.documents[item.id]
            score = 0.0
            for token, qtf in query_terms.items():
                term_frequency = terms.get(token, 0)
                if not term_frequency:
                    continue
                inverse_document_frequency = math.log((total + 1) / (self.df[token] + 1)) + 1
                score += qtf * (1 + math.log(term_frequency)) * inverse_document_frequency
            if score:
                scored.append((item, score * (0.5 + item.source_quality_score / 2)))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return [Citation(item.id, item.title, item.canonical_url, item.source_excerpt[:500], round(score, 3)) for item, score in scored[:limit]]

    def answer(self, query: str) -> RAGAnswer:
        citations = self.retrieve(query)
        if not citations:
            return RAGAnswer("لا توجد أدلة كافية في القاعدة المحلية للإجابة بدقة.", [], 0.0, ["أدخل مصدرًا موثقًا أو عدّل صياغة الاستعلام."])
        confidence = min(0.90, 0.40 + 0.10 * len(citations) + citations[0].score / 20)
        return RAGAnswer(
            "تم العثور على أدلة مرتبطة بالسؤال. اقرأ الاستشهادات ولا تعتمد قرارًا عالي الأثر قبل مراجعة الأدلة المضادة.",
            citations,
            round(confidence, 2),
            ["الإجابة استرجاعية ومسنَدة بالمصادر فقط.", "لا تستنتج نية خاصة أو سمة نفسية من المادة.", "تحتاج القرارات العالية الأثر مراجعة مستقلة."],
        )


# ---------------------------------------------------------------------------
# Deliverable factory: knowledge base, encyclopedia, decision trees, prompts,
# checklists, SOPs, playbooks, and pattern catalogues — all evidence linked.
# ---------------------------------------------------------------------------


class ArtifactFactory:
    """Builds useful operational artifacts without inventing uncited facts."""

    def knowledge_base(self, subject_id: str, evidence: list[Evidence], claims: list[Claim]) -> dict[str, Any]:
        subject_evidence = [item for item in evidence if item.subject_id == subject_id]
        subject_claims = [item for item in claims if item.subject_id == subject_id]
        by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for claim in subject_claims:
            by_kind[claim.kind.value].append(claim.to_dict())
        return {
            "type": "knowledge_base",
            "subject_id": subject_id,
            "evidence_count": len(subject_evidence),
            "claims_by_analysis": dict(by_kind),
            "ranked_principles": PatternSynthesizer().ranked_principles(subject_claims),
            "sources": [{"evidence_id": item.id, "title": item.title, "url": item.canonical_url, "type": item.source_type.value} for item in subject_evidence],
            "provenance_rule": "Every claim must link to one or more evidence IDs.",
        }

    def encyclopedia(self, subject_id: str, evidence: list[Evidence], claims: list[Claim]) -> dict[str, Any]:
        base = self.knowledge_base(subject_id, evidence, claims)
        sections: list[dict[str, Any]] = []
        for kind, items in sorted(base["claims_by_analysis"].items()):
            sections.append({"heading": kind.replace("_", " ").title(), "observations": [item["statement"] for item in items], "evidence_ids": sorted({identifier for item in items for identifier in item["evidence_ids"]})})
        return {"type": "research_encyclopedia", "subject_id": subject_id, "sections": sections, "limitations": ["Sections are derived from available evidence and can be incomplete."]}

    def decision_tree(self, rule: OperationalRule | None = None) -> dict[str, Any]:
        trigger = rule.trigger if rule else "A product, research, engineering, or operational decision"
        action = rule.recommended_action if rule else "Use the guarded decision workflow"
        return {
            "type": "decision_tree",
            "root": trigger,
            "nodes": [
                {"question": "Is the impact high?", "yes": "Check evidence strength and independent review", "no": "Run standard quality checks"},
                {"question": "Is evidence below 0.75?", "yes": "Run a small measurable experiment", "no": "Check reversibility and release controls"},
                {"question": "Is change hard to reverse?", "yes": "Architecture, risk, security, and rollback review", "no": "Progressive release with monitoring"},
            ],
            "recommended_action": action,
            "evidence_ids": rule.evidence_ids if rule else [],
        }

    def professional_prompt(self, subject_id: str, artifact_type: str = "research") -> dict[str, Any]:
        return {
            "type": "professional_prompt",
            "subject_id": subject_id,
            "prompt": (
                f"Act as the EFI-OS {artifact_type} assistant for subject '{subject_id}'. Use only retrieved evidence. "
                "For each material claim, cite evidence IDs and URLs, report confidence, identify limitations and counter-evidence, "
                "and never infer private intent, personality, or undisclosed information. If evidence is insufficient, say so and propose the next permitted research step."
            ),
        }

    def checklist(self, discipline: str) -> dict[str, Any]:
        common = ["Requirement and scope are recorded", "Evidence/provenance is linked", "Independent review is complete", "Decision and rationale are logged"]
        library = {
            "testing": ["Unit tests pass", "Integration tests pass", "Regression suite passes", "Negative/edge cases covered", "Test artifacts retained"],
            "security": ["Threat model reviewed", "Secrets scan clean", "Dependency/SBOM scan reviewed", "Access controls tested", "Rollback and incident plan ready"],
            "architecture": ["Requirements traceability checked", "Interfaces reviewed", "Failure modes documented", "Scalability and observability designed", "ADR approved"],
            "research": ["Source authority checked", "License/access basis recorded", "Identity resolved", "Counter-evidence sought", "Confidence and limitations reported"],
            "release": ["Tests pass", "Security review complete", "Privacy review complete", "Progressive rollout configured", "Monitoring and rollback ready"],
        }
        return {"type": "checklist", "discipline": discipline, "items": common + library.get(discipline, library["research"])}

    def engineering_playbook(self, topic: str) -> dict[str, Any]:
        patterns = {
            "architecture": ["Frame constraints", "Define quality attributes", "Create alternatives", "Threat-model and review", "Record ADR", "Verify traceability"],
            "testing": ["Test at the lowest viable level", "Automate fast checks", "Add integration and end-to-end paths", "Test failure modes", "Measure flakiness", "Gate release"],
            "security": ["Define assets and trust boundaries", "Threat-model", "Implement least privilege", "Scan code/dependencies/secrets", "Test abuse cases", "Monitor and respond"],
            "code": ["Write small cohesive change", "Add tests", "Run formatting/static checks", "Peer review", "Measure regression risk", "Document decision"],
            "failure": ["Contain incident", "Preserve evidence", "Restore safely", "Perform blameless postmortem", "Implement corrective action", "Verify recurrence prevention"],
            "innovation": ["State opportunity", "Rank assumptions by risk", "Prototype smallest test", "Define measurement", "Decide scale/pivot/stop", "Capture learning"],
        }
        return {"type": "engineering_playbook", "topic": topic, "steps": patterns.get(topic, patterns["innovation"]), "checklist": self.checklist("architecture" if topic == "architecture" else "research")}

    def pattern_catalog(self, claims: list[Claim]) -> dict[str, Any]:
        mapping = {
            "architecture_patterns": {AnalysisKind.DESIGN_REVIEW, AnalysisKind.ENGINEERING_MANAGEMENT},
            "testing_patterns": {AnalysisKind.TESTING_QUALITY, AnalysisKind.EXPERIMENTATION},
            "security_patterns": {AnalysisKind.CYBERSECURITY, AnalysisKind.RISK_MANAGEMENT},
            "code_patterns": {AnalysisKind.CODE_METHOD, AnalysisKind.CODE_REVIEW, AnalysisKind.AUTOMATION},
            "failure_patterns": {AnalysisKind.FAILURE_RECOVERY, AnalysisKind.DECISION_CRISIS},
            "innovation_patterns": {AnalysisKind.PRODUCT_METHOD, AnalysisKind.EXPERIMENTATION, AnalysisKind.HYPOTHESIS_REVIEW},
        }
        return {
            name: [claim.to_dict() for claim in claims if claim.kind in kinds]
            for name, kinds in mapping.items()
        }

    def build(self, kind: str, *, subject_id: str, evidence: list[Evidence], claims: list[Claim], rule: OperationalRule | None = None, topic: str = "innovation") -> dict[str, Any]:
        if kind == "knowledge_base":
            return self.knowledge_base(subject_id, evidence, claims)
        if kind == "encyclopedia":
            return self.encyclopedia(subject_id, evidence, claims)
        if kind == "decision_tree":
            return self.decision_tree(rule)
        if kind == "prompt":
            return self.professional_prompt(subject_id)
        if kind == "checklist":
            return self.checklist(topic)
        if kind == "playbook":
            return self.engineering_playbook(topic)
        if kind == "patterns":
            return {"type": "pattern_catalog", "subject_id": subject_id, "catalog": self.pattern_catalog([claim for claim in claims if claim.subject_id == subject_id])}
        raise ValueError("Artifact kind must be one of: knowledge_base, encyclopedia, decision_tree, prompt, checklist, playbook, patterns")


# ---------------------------------------------------------------------------
# Incremental update monitor: tracked authorised sources, fingerprints, and
# re-analysis only when content changes. No API keys are necessary.
# ---------------------------------------------------------------------------


class UpdateMonitor:
    def __init__(self, store: KnowledgeStore) -> None:
        self.store = store

    def register(self, *, subject_id: str, url: str, source_type: SourceType, language: str = "und", access_basis: str = "public page permitted by source terms", allowed_domains: list[str] | None = None) -> dict[str, Any]:
        return self.store.save_watch({
            "subject_id": subject_id,
            "url": url,
            "source_type": source_type.value,
            "language": language,
            "access_basis": access_basis,
            "allowed_domains": allowed_domains or [],
        })

    @staticmethod
    def fingerprint(evidence: Evidence) -> str:
        return hashlib.sha256(evidence.normalized_text.encode("utf-8")).hexdigest()

    def check(self, orchestrator: "ResearchOrchestrator") -> list[dict[str, Any]]:
        outcomes: list[dict[str, Any]] = []
        for watch in self.store.list_watches():
            try:
                evidence = PublicURLConnector(WebPolicy(set(watch.get("allowed_domains", [])))).ingest(
                    subject_id=watch["subject_id"], url=watch["url"], source_type=SourceType(watch["source_type"]),
                    language=watch["language"], access_basis=watch["access_basis"],
                )
                fingerprint = self.fingerprint(evidence)
                changed = fingerprint != watch.get("last_fingerprint")
                watch["last_fingerprint"] = fingerprint
                watch["last_checked_at"] = now_iso()
                self.store.save_watch(watch)
                if changed:
                    # Keep historical snapshots distinct while preserving the original source URL in provenance.
                    evidence.canonical_url = f"{watch['url']}#efi-snapshot-{fingerprint[:12]}"
                    evidence.provenance["source_url"] = watch["url"]
                    run = orchestrator.process(evidence)
                    outcomes.append({"watch_id": watch["id"], "changed": True, "evidence_id": evidence.id, "claim_ids": run.claim_ids})
                else:
                    outcomes.append({"watch_id": watch["id"], "changed": False})
            except Exception as error:
                outcomes.append({"watch_id": watch["id"], "changed": None, "error": str(error)})
        self.store.audit("update_monitor_checked", {"outcomes": outcomes})
        return outcomes


# ---------------------------------------------------------------------------
# Rule engine, SOP/workflow compiler, and release gates
# ---------------------------------------------------------------------------


class RuleCompiler:
    def compile(self, claim: Claim, *, name: str, trigger: str, action: str, applicability: list[str], exclusions: list[str], counter_evidence_reviewed: bool) -> OperationalRule:
        rule = OperationalRule(
            name=name,
            category=claim.kind.value,
            trigger=trigger,
            recommended_action=action,
            rationale=claim.statement,
            evidence_ids=claim.evidence_ids,
            confidence=claim.confidence,
            applicability=applicability,
            exclusions=exclusions,
            counter_evidence_reviewed=counter_evidence_reviewed,
        )
        RULE_GATE.evaluate(rule.to_dict()).require_passed()
        return rule


class RuleEngine:
    def __init__(self, rules: list[OperationalRule]) -> None:
        self.rules = rules

    def evaluate(self, context: dict[str, str]) -> dict[str, Any]:
        searchable = " ".join(str(value).casefold() for value in context.values())
        domain = str(context.get("domain", "")).casefold()
        matched: list[OperationalRule] = []
        for rule in self.rules:
            trigger_terms = [word for word in _tokens(rule.trigger) if len(word) > 2]
            excluded = any(exclusion.casefold() in searchable for exclusion in rule.exclusions)
            applies = not rule.applicability or domain in [value.casefold() for value in rule.applicability]
            if applies and not excluded and any(term in searchable for term in trigger_terms):
                matched.append(rule)
        return {
            "matched_rule_ids": [rule.id for rule in matched],
            "recommended_actions": [rule.recommended_action for rule in matched],
            "warnings": [] if matched else ["No approved rule matched. Escalate to a human review workflow."],
        }


class DecisionWorkflow:
    """Operational decision tree with mandatory engineering gates."""

    def evaluate(self, *, impact: str, evidence_strength: float, reversibility: str, security_reviewed: bool, tests_passed: bool = False, privacy_reviewed: bool = False, rollback_ready: bool = False, observability_ready: bool = False) -> WorkflowResult:
        if not 0 <= evidence_strength <= 1:
            raise ValueError("evidence_strength must be between 0 and 1")
        if impact.casefold() == "high" and evidence_strength < 0.75:
            return WorkflowResult(
                "require_experiment",
                ["Define testable assumptions", "Design minimum measurable experiment", "Set success and rollback thresholds", "Run independent evidence review"],
                False,
                "High-impact decision lacks sufficient evidence.",
            )
        if reversibility.casefold() == "low" and not security_reviewed:
            return WorkflowResult(
                "require_architecture_and_security_review",
                ["Threat model", "Architecture review", "Risk register", "Rollback plan", "Approval record"],
                False,
                "Low-reversibility change cannot proceed without security review.",
            )
        final_gate = release_gate(
            tests_passed=tests_passed,
            security_reviewed=security_reviewed,
            privacy_reviewed=privacy_reviewed,
            rollback_ready=rollback_ready,
            observability_ready=observability_ready,
        )
        if not final_gate.passed:
            return WorkflowResult(
                "complete_release_gate",
                ["Resolve every release-gate finding", "Re-run tests and approval checks", "Deploy progressively behind a feature flag"],
                False,
                "Evidence is adequate, but operational release controls are incomplete.",
                [final_gate],
            )
        return WorkflowResult(
            "progressive_release",
            ["Deploy to a small cohort", "Monitor error, latency, quality, and security telemetry", "Expand gradually", "Keep rollback available", "Record learning"],
            True,
            "Evidence and operational controls meet the release policy.",
            [final_gate],
        )


def make_sop(rule: OperationalRule) -> dict[str, Any]:
    return {
        "title": f"SOP: {rule.name}",
        "trigger": rule.trigger,
        "preconditions": ["Evidence links are available", "Counter-evidence review is recorded", "Scope is within applicability"],
        "procedure": [rule.recommended_action, "Record outcome and deviations", "Review the rule after material new evidence"],
        "exceptions": rule.exclusions,
        "evidence_ids": rule.evidence_ids,
        "version": rule.version,
    }


# ---------------------------------------------------------------------------
# Multi-agent orchestration with a distinct critic and explicit state gates
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class AgentRun:
    evidence_id: str
    claim_ids: list[str]
    possible_conflicts: list[dict[str, Any]]
    stage_log: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ResearchOrchestrator:
    """Collector -> verifier -> analyst -> critic -> knowledge writer; each stage is auditable."""

    def __init__(self, store: KnowledgeStore) -> None:
        self.store = store
        self.analyzer = EvidenceAnalyzer()
        self.critic = CriticAgent()

    def process(self, evidence: Evidence, requested: list[AnalysisKind] | None = None) -> AgentRun:
        stages = ["collector:received"]
        source = SOURCE_GATE.evaluate(evidence.to_dict())
        source.require_passed()
        stages.append("verifier:source-gate-passed")
        content = EVIDENCE_GATE.evaluate(evidence.to_dict())
        content.require_passed()
        stages.append("verifier:evidence-gate-passed")
        self.store.save_evidence(evidence)
        stages.append("knowledge-agent:evidence-persisted")
        claims = self.analyzer.analyze(evidence, requested)
        self.store.save_claims(claims)
        stages.append(f"analysis-agent:claims-extracted={len(claims)}")
        conflicts = self.critic.find_possible_conflicts(claims)
        stages.append(f"critic-agent:possible-conflicts={len(conflicts)}")
        self.store.audit("agent_run", {"evidence_id": evidence.id, "claims": [claim.id for claim in claims], "conflicts": conflicts})
        return AgentRun(evidence.id, [claim.id for claim in claims], conflicts, stages)


# ---------------------------------------------------------------------------
# Unified application service and API
# ---------------------------------------------------------------------------


class EFIApplication:
    def __init__(self, database_path: str | Path = DEFAULT_DATABASE) -> None:
        self.store = KnowledgeStore(database_path)
        self.orchestrator = ResearchOrchestrator(self.store)
        self.workflow = DecisionWorkflow()
        self.artifacts = ArtifactFactory()
        self.updater = UpdateMonitor(self.store)

    def health(self) -> dict[str, Any]:
        return {"status": "ok", "service": APP_NAME, "version": APP_VERSION, "storage": "local SQLite", "external_api_keys_required": False, "stats": self.store.stats()}

    def capabilities(self) -> dict[str, Any]:
        return {"service": APP_NAME, "single_file": True, "external_api_keys_required": False, "capabilities": CAPABILITY_REGISTRY}

    def create_evidence(self, payload: dict[str, Any]) -> dict[str, Any]:
        evidence_payload = dict(payload)
        requested_values = evidence_payload.pop("requested_analyses", [])
        evidence = Evidence.from_dict(evidence_payload)
        requested = [AnalysisKind(item) for item in requested_values] if requested_values else None
        run = self.orchestrator.process(evidence, requested)
        return {"evidence": evidence.to_dict(), "agent_run": run.to_dict(), "claims": [claim.to_dict() for claim in self._claims_from_ids(run.claim_ids)]}

    def ingest_local_file(self, *, subject_id: str, path: str, source_type: str, language: str = "und") -> dict[str, Any]:
        evidence = LocalFileConnector().ingest(subject_id=subject_id, path=path, source_type=SourceType(source_type), language=language)
        run = self.orchestrator.process(evidence)
        return {"evidence": evidence.to_dict(), "agent_run": run.to_dict()}

    def ingest_url(self, payload: dict[str, Any]) -> dict[str, Any]:
        connector = PublicURLConnector(WebPolicy(set(payload.get("allowed_domains", []))))
        evidence = connector.ingest(
            subject_id=payload["subject_id"], url=payload["url"], source_type=SourceType(payload.get("source_type", "article")),
            language=payload.get("language", "und"), quality=float(payload.get("quality", 0.60)), access_basis=payload.get("access_basis", "public page permitted by source terms"),
        )
        run = self.orchestrator.process(evidence)
        return {"evidence": evidence.to_dict(), "agent_run": run.to_dict()}

    def crawl_sources(self, payload: dict[str, Any]) -> dict[str, Any]:
        crawler = ApprovedDomainCrawler(WebPolicy(set(payload.get("allowed_domains", []))), int(payload.get("max_pages", 20)))
        gathered = crawler.crawl(
            subject_id=payload["subject_id"], seed_urls=payload["seed_urls"], source_type=SourceType(payload.get("source_type", "article")),
            language=payload.get("language", "und"), query=payload.get("query", ""), access_basis=payload.get("access_basis", "public pages permitted by source terms"),
        )
        runs = [self.orchestrator.process(evidence).to_dict() for evidence in gathered]
        return {"evidence_count": len(gathered), "evidence": [item.to_dict() for item in gathered], "agent_runs": runs}

    def analyze_subject(self, subject_id: str, requested: list[str] | None = None) -> dict[str, Any]:
        requested_kinds = [AnalysisKind(item) for item in requested] if requested else None
        all_runs = []
        for evidence in self.store.list_evidence(subject_id):
            claims = self.orchestrator.analyzer.analyze(evidence, requested_kinds)
            self.store.save_claims(claims)
            all_runs.extend(claims)
        patterns = PatternSynthesizer().recurring_patterns(self.store.list_claims(subject_id))
        return {"subject_id": subject_id, "new_claims": [claim.to_dict() for claim in all_runs], "recurring_patterns": patterns}

    def research(self, query: str, subject_id: str | None = None) -> dict[str, Any]:
        return LocalRAG(self.store.list_evidence(subject_id)).answer(query).to_dict()

    def compare(self, left_subject: str, right_subject: str) -> dict[str, Any]:
        return PatternSynthesizer().compare_subjects(left_subject, right_subject, self.store.list_claims())

    def compile_rule(self, payload: dict[str, Any]) -> dict[str, Any]:
        claim = self.store.get_claim(payload["claim_id"])
        if not claim:
            raise KeyError("Claim not found")
        rule = RuleCompiler().compile(
            claim,
            name=payload["name"], trigger=payload["trigger"], action=payload["action"],
            applicability=payload.get("applicability", []), exclusions=payload.get("exclusions", []),
            counter_evidence_reviewed=bool(payload.get("counter_evidence_reviewed", False)),
        )
        self.store.save_rule(rule)
        return {"rule": rule.to_dict(), "sop": make_sop(rule)}

    def evaluate_rules(self, context: dict[str, str]) -> dict[str, Any]:
        return RuleEngine(self.store.list_rules()).evaluate(context)

    def evaluate_workflow(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.workflow.evaluate(
            impact=payload["impact"], evidence_strength=float(payload["evidence_strength"]), reversibility=payload["reversibility"],
            security_reviewed=bool(payload.get("security_reviewed", False)), tests_passed=bool(payload.get("tests_passed", False)),
            privacy_reviewed=bool(payload.get("privacy_reviewed", False)), rollback_ready=bool(payload.get("rollback_ready", False)), observability_ready=bool(payload.get("observability_ready", False)),
        ).to_dict()

    def plan_research(self, payload: dict[str, Any]) -> dict[str, Any]:
        return QueryPlanner().build(
            objective=payload["objective"], names=payload["names"], languages=payload.get("languages", ["und"]),
            topic_terms=payload["topic_terms"], aliases=payload.get("aliases", {}),
        ).to_dict()

    def generate_artifact(self, payload: dict[str, Any]) -> dict[str, Any]:
        rule = self.store.list_rules()
        selected_rule = next((item for item in rule if item.id == payload.get("rule_id")), None)
        return self.artifacts.build(
            payload["kind"],
            subject_id=payload["subject_id"],
            evidence=self.store.list_evidence(),
            claims=self.store.list_claims(),
            rule=selected_rule,
            topic=payload.get("topic", "innovation"),
        )

    def register_update_source(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.updater.register(
            subject_id=payload["subject_id"], url=payload["url"], source_type=SourceType(payload.get("source_type", "article")),
            language=payload.get("language", "und"), access_basis=payload.get("access_basis", "public page permitted by source terms"),
            allowed_domains=payload.get("allowed_domains", []),
        )

    def check_updates(self) -> dict[str, Any]:
        return {"outcomes": self.updater.check(self.orchestrator)}

    def _claims_from_ids(self, identifiers: list[str]) -> list[Claim]:
        return [claim for identifier in identifiers if (claim := self.store.get_claim(identifier))]


def build_server(app: EFIApplication, host: str = "127.0.0.1", port: int = 8080) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            raw = json.dumps(serialise(payload), ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _read_json(self) -> dict[str, Any]:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 1 or size > 2_000_000:
                raise ValueError("Request JSON must be between 1 byte and 2 MB")
            value = json.loads(self.rfile.read(size))
            if not isinstance(value, dict):
                raise ValueError("JSON payload must be an object")
            return value

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self._send(HTTPStatus.OK, app.health())
            elif parsed.path == "/capabilities":
                self._send(HTTPStatus.OK, app.capabilities())
            elif parsed.path == "/research":
                params = parse_qs(parsed.query)
                self._send(HTTPStatus.OK, app.research(params.get("query", [""])[0], params.get("subject_id", [None])[0]))
            else:
                self._send(HTTPStatus.NOT_FOUND, {"error": "Not found"})

        def do_POST(self) -> None:  # noqa: N802
            try:
                data = self._read_json()
                routes: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
                    "/evidence": app.create_evidence,
                    "/sources/fetch": app.ingest_url,
                    "/sources/crawl": app.crawl_sources,
                    "/research/plan": app.plan_research,
                    "/analyze": lambda payload: app.analyze_subject(payload["subject_id"], payload.get("analyses")),
                    "/compare": lambda payload: app.compare(payload["left_subject"], payload["right_subject"]),
                    "/rules/compile": app.compile_rule,
                    "/rules/evaluate": lambda payload: app.evaluate_rules(payload["context"]),
                    "/workflows/evaluate": app.evaluate_workflow,
                    "/artifacts/generate": app.generate_artifact,
                    "/updates/register": app.register_update_source,
                    "/updates/check": lambda payload: app.check_updates(),
                }
                if self.path not in routes:
                    self._send(HTTPStatus.NOT_FOUND, {"error": "Not found"})
                    return
                self._send(HTTPStatus.OK, routes[self.path](data))
            except (KeyError, TypeError, ValueError, PermissionError, FileNotFoundError) as error:
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            except Exception:
                self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Internal server error; inspect local audit log."})

        def log_message(self, fmt: str, *args: Any) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)


# ---------------------------------------------------------------------------
# CLI and embedded tests
# ---------------------------------------------------------------------------


def print_json(value: Any) -> None:
    print(json.dumps(serialise(value), ensure_ascii=False, indent=2))


def demo(app: EFIApplication) -> None:
    evidence = Evidence(
        subject_id="demo-founder", source_type=SourceType.INTERVIEW, title="Demo: evidence-driven engineering",
        canonical_url="https://example.org/demo-interview",
        normalized_text=(
            "We decide by first identifying the highest-risk assumption and the evidence missing. "
            "Before a broad product launch, we test the hypothesis with a small experiment and measure the result. "
            "After a production failure, the engineering team added automated tests, a security review, monitoring, and a rollback path for every release."
        ),
        source_excerpt="We decide by first identifying the highest-risk assumption and the evidence missing.",
        original_language="en", author_or_speaker="Demo Founder", license_or_access_basis="embedded demo data", source_quality_score=0.95,
        provenance={"connector": "demo", "reviewed": True},
    )
    run = app.orchestrator.process(evidence)
    print_json({"agent_run": run.to_dict(), "research": app.research("hypothesis experiment product launch", "demo-founder"), "health": app.health()})


class EFIOSSelfTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.app = EFIApplication(Path(self.temp.name) / "knowledge.db")
        self.evidence = Evidence(
            subject_id="founder-a", source_type=SourceType.INTERVIEW, title="Evidence fixture", canonical_url="https://example.org/fixture",
            normalized_text=("We decide after ranking the highest risk. We test the hypothesis before a product launch. "
                             "After an incident, the team added a security review and rollback procedure."),
            source_excerpt="We test the hypothesis before a product launch.", license_or_access_basis="test fixture", source_quality_score=0.95,
            provenance={"fixture": True},
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_full_evidence_to_rag_flow(self) -> None:
        run = self.app.orchestrator.process(self.evidence)
        self.assertGreaterEqual(len(run.claim_ids), 3)
        answer = self.app.research("test hypothesis product launch", "founder-a")
        self.assertGreater(answer["confidence"], 0)
        self.assertEqual(answer["citations"][0]["evidence_id"], self.evidence.id)

    def test_rule_requires_independent_review(self) -> None:
        run = self.app.orchestrator.process(self.evidence)
        claim = self.app.store.get_claim(run.claim_ids[0])
        assert claim is not None
        with self.assertRaises(ValueError):
            RuleCompiler().compile(claim, name="Test first", trigger="high impact", action="Run a measured experiment", applicability=["product"], exclusions=[], counter_evidence_reviewed=False)

    def test_high_impact_workflow_is_blocked(self) -> None:
        result = self.app.evaluate_workflow({"impact": "high", "evidence_strength": 0.40, "reversibility": "high", "security_reviewed": True})
        self.assertFalse(result["release_allowed"])
        self.assertEqual(result["decision"], "require_experiment")

    def test_release_gate_requires_all_operational_controls(self) -> None:
        result = self.app.evaluate_workflow({"impact": "medium", "evidence_strength": 0.9, "reversibility": "high", "security_reviewed": True})
        self.assertFalse(result["release_allowed"])
        self.assertEqual(result["decision"], "complete_release_gate")

    def test_local_file_and_multilingual_plan_need_no_key(self) -> None:
        file = Path(self.temp.name) / "arabic.txt"
        file.write_text("يجب اختبار الفرضية قبل إطلاق المنتج مع قياس النتائج وتوثيق القرار.", encoding="utf-8")
        loaded = LocalFileConnector().ingest(subject_id="founder-b", path=file, source_type=SourceType.ARTICLE, language="ar")
        self.assertIn("local.efi-os.invalid", loaded.canonical_url)
        plan = QueryPlanner().build(objective="تحليل القرار", names=["الاسم"], languages=["ar", "en"], topic_terms=["decision", "قرار"])
        self.assertGreaterEqual(len(plan.queries), 6)

    def test_rank_fusion(self) -> None:
        result = reciprocal_rank_fusion({"lexical": ["a", "b"], "semantic": ["b", "a"]})
        self.assertEqual(result[0]["document_id"], "a")
        self.assertEqual(len(result[0]["ranked_by"]), 2)

    def test_artifacts_and_update_registry(self) -> None:
        self.app.orchestrator.process(self.evidence)
        encyclopedia = self.app.generate_artifact({"kind": "encyclopedia", "subject_id": "founder-a"})
        playbook = self.app.generate_artifact({"kind": "playbook", "subject_id": "founder-a", "topic": "security"})
        self.assertEqual(encyclopedia["type"], "research_encyclopedia")
        self.assertIn("Threat-model", playbook["steps"])
        watch = self.app.register_update_source({"subject_id": "founder-a", "url": "https://example.org/updates", "source_type": "article", "allowed_domains": ["example.org"]})
        self.assertEqual(watch["subject_id"], "founder-a")
        self.assertEqual(self.app.health()["stats"]["source_watches"], 1)

    def test_explicit_api_evidence_supports_requested_analyses(self) -> None:
        payload = self.evidence.to_dict()
        payload["requested_analyses"] = [AnalysisKind.HYPOTHESIS_REVIEW.value]
        result = self.app.create_evidence(payload)
        self.assertTrue(result["claims"])
        self.assertTrue(all(claim["kind"] == AnalysisKind.HYPOTHESIS_REVIEW.value for claim in result["claims"]))

    def test_local_http_api_health_and_research_plan(self) -> None:
        server = build_server(self.app, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            with urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as response:
                health = json.loads(response.read())
            self.assertEqual(health["external_api_keys_required"], False)
            payload = json.dumps({"objective": "research", "names": ["Founder A"], "languages": ["en", "ar"], "topic_terms": ["decision"]}).encode("utf-8")
            request = Request(f"http://127.0.0.1:{port}/research/plan", data=payload, method="POST", headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=5) as response:
                plan = json.loads(response.read())
            self.assertTrue(plan["queries"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_incremental_update_monitor_detects_only_changed_content(self) -> None:
        class FeedHandler(BaseHTTPRequestHandler):
            content = "Release note: test the hypothesis before release and document the measured result."

            def do_GET(self) -> None:  # noqa: N802
                body = self.content.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, fmt: str, *args: Any) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), FeedHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/release"
            self.app.register_update_source({"subject_id": "founder-a", "url": url, "source_type": "release_note", "allowed_domains": ["127.0.0.1"]})
            first = self.app.check_updates()["outcomes"][0]
            second = self.app.check_updates()["outcomes"][0]
            FeedHandler.content = "Release note: security review and rollback are required after an incident."
            third = self.app.check_updates()["outcomes"][0]
            self.assertTrue(first["changed"])
            self.assertFalse(second["changed"])
            self.assertTrue(third["changed"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_authorised_crawler_respects_robots_and_collects_linked_pages(self) -> None:
        class SiteHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/robots.txt":
                    body = b"User-agent: *\nAllow: /\n"
                    content_type = "text/plain"
                elif self.path == "/":
                    body = b"<html><title>Seed</title><body>Engineering research index with documented public source material for analysis <a href='/detail'>detail</a></body></html>"
                    content_type = "text/html"
                else:
                    body = b"<html><title>Detail</title><body>Test the hypothesis before product release.</body></html>"
                    content_type = "text/html"
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", f"{content_type}; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, fmt: str, *args: Any) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), SiteHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            seed = f"http://127.0.0.1:{server.server_address[1]}/"
            crawler = ApprovedDomainCrawler(WebPolicy({"127.0.0.1"}), max_pages=4)
            pages = crawler.crawl(subject_id="founder-a", seed_urls=[seed], query="hypothesis")
            self.assertEqual(len(pages), 2)
            self.assertEqual(pages[0].title, "Detail")
            self.assertTrue(all(page.provenance["robots_checked"] for page in pages))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_validation_rejects_invalid_evidence_early(self) -> None:
        with self.assertRaises(ValueError):
            Evidence(
                subject_id="founder-a", source_type=SourceType.ARTICLE, title="Invalid", canonical_url="not-a-url",
                normalized_text="This source deliberately has enough text to reach validation.", source_excerpt="invalid",
                provenance={"fixture": True},
            )
        with self.assertRaises(ValueError):
            Evidence(
                subject_id="founder-a", source_type=SourceType.ARTICLE, title="Short", canonical_url="https://example.org/short",
                normalized_text="too short", source_excerpt="short", provenance={"fixture": True},
            )

    def test_sqlite_persistence_and_audit_survive_reopen(self) -> None:
        self.app.orchestrator.process(self.evidence)
        reopened = EFIApplication(self.app.store.path)
        stored = reopened.store.list_evidence("founder-a")
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].canonical_url, self.evidence.canonical_url)
        self.assertGreaterEqual(reopened.health()["stats"]["audit_log"], 2)

    def test_local_git_repository_analysis_without_remote_access(self) -> None:
        repository = Path(self.temp.name) / "repository"
        repository.mkdir()
        (repository / "service.py").write_text(
            "def evaluate_risk(value):\n    if value > 3:\n        return 'rollback'\n    return 'release'\n",
            encoding="utf-8",
        )
        (repository / "README.md").write_text("# Release\nTests and security review are required before release.", encoding="utf-8")
        evidence = LocalGitConnector().ingest(subject_id="founder-a", repository=repository)
        self.assertEqual(evidence.source_type, SourceType.GITHUB_REPOSITORY)
        self.assertIn("evaluate_risk", evidence.normalized_text)
        self.assertTrue(evidence.provenance["local_export"])

    def test_rule_engine_sop_and_low_confidence_gate(self) -> None:
        run = self.app.orchestrator.process(self.evidence)
        claim = self.app.store.get_claim(run.claim_ids[0])
        assert claim is not None
        approved = RuleCompiler().compile(
            claim, name="Experiment before scale", trigger="high impact decision", action="Run a bounded experiment with success and rollback criteria.",
            applicability=["product"], exclusions=["security emergency"], counter_evidence_reviewed=True,
        )
        self.app.store.save_rule(approved)
        decision = self.app.evaluate_rules({"domain": "product", "scenario": "high impact decision"})
        self.assertIn(approved.id, decision["matched_rule_ids"])
        self.assertEqual(make_sop(approved)["title"], "SOP: Experiment before scale")
        weak = Claim("founder-a", AnalysisKind.EXPERIMENTATION, "A weak observation with a single evidence item.", [self.evidence.id], 0.40, ["Weak confidence."])
        with self.assertRaises(ValueError):
            RuleCompiler().compile(weak, name="Weak rule", trigger="decision", action="Do something", applicability=["product"], exclusions=[], counter_evidence_reviewed=True)

    def test_comparison_ranking_artifacts_and_empty_rag(self) -> None:
        self.app.orchestrator.process(self.evidence)
        second = Evidence(
            subject_id="founder-b", source_type=SourceType.ARTICLE, title="Second founder", canonical_url="https://example.org/second",
            normalized_text="We decide by testing the hypothesis and measuring the product impact before launch.", source_excerpt="We decide by testing the hypothesis.",
            license_or_access_basis="test fixture", source_quality_score=0.90, provenance={"fixture": True},
        )
        self.app.orchestrator.process(second)
        comparison = self.app.compare("founder-a", "founder-b")
        self.assertIn(AnalysisKind.HYPOTHESIS_REVIEW.value, comparison["common_analytical_categories"])
        knowledge = self.app.generate_artifact({"kind": "knowledge_base", "subject_id": "founder-a"})
        self.assertIn("ranked_principles", knowledge)
        self.assertEqual(LocalRAG([]).answer("anything").confidence, 0.0)
        for kind in ("decision_tree", "prompt", "checklist", "playbook", "patterns"):
            artifact = self.app.generate_artifact({"kind": kind, "subject_id": "founder-a", "topic": "security"})
            self.assertTrue(artifact)

    def test_crawler_fails_closed_when_robots_disallow(self) -> None:
        class DisallowHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/robots.txt":
                    body = b"User-agent: *\nDisallow: /\n"
                    content_type = "text/plain"
                else:
                    body = b"<html><title>Denied</title><body>Content that must never be ingested by crawler.</body></html>"
                    content_type = "text/html"
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", f"{content_type}; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, fmt: str, *args: Any) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), DisallowHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            seed = f"http://127.0.0.1:{server.server_address[1]}/"
            self.assertEqual(ApprovedDomainCrawler(WebPolicy({"127.0.0.1"})).crawl(subject_id="founder-a", seed_urls=[seed]), [])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_local_tool_connectors_fail_safely_for_invalid_input(self) -> None:
        with self.assertRaises(ValueError):
            LocalToolConnector.pdf_to_text(Path(self.temp.name) / "missing.pdf", Path(self.temp.name) / "out.txt")
        with self.assertRaises(ValueError):
            LocalToolConnector.transcribe(Path(self.temp.name) / "missing.mp3", Path(self.temp.name) / "out.txt", ["local-transcriber"])

    def test_http_api_evidence_and_workflow_contract(self) -> None:
        server = build_server(self.app, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            payload = self.evidence.to_dict()
            payload["requested_analyses"] = [AnalysisKind.HYPOTHESIS_REVIEW.value]
            request = Request(f"http://127.0.0.1:{port}/evidence", data=json.dumps(payload).encode("utf-8"), method="POST", headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=5) as response:
                created = json.loads(response.read())
            self.assertEqual(created["claims"][0]["kind"], AnalysisKind.HYPOTHESIS_REVIEW.value)
            workflow_payload = {"impact": "medium", "evidence_strength": 0.9, "reversibility": "high", "security_reviewed": True, "tests_passed": True, "privacy_reviewed": True, "rollback_ready": True, "observability_ready": True}
            request = Request(f"http://127.0.0.1:{port}/workflows/evaluate", data=json.dumps(workflow_payload).encode("utf-8"), method="POST", headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=5) as response:
                workflow = json.loads(response.read())
            self.assertTrue(workflow["release_allowed"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} {APP_VERSION}: local, evidence-driven research system")
    parser.add_argument("--database", default=DEFAULT_DATABASE, help="Local SQLite knowledge-base path")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("self-test", help="Run all embedded validation tests")
    commands.add_parser("capabilities", help="Print the requirement-to-component traceability matrix")
    commands.add_parser("demo", help="Run local evidence-to-RAG demonstration")
    ingest = commands.add_parser("ingest-file", help="Ingest a local txt/md/html/json source")
    ingest.add_argument("--subject", required=True)
    ingest.add_argument("--path", required=True)
    ingest.add_argument("--type", required=True, choices=[kind.value for kind in SourceType])
    ingest.add_argument("--language", default="und")
    web = commands.add_parser("ingest-url", help="Ingest one explicit authorised public URL; no API key")
    web.add_argument("--subject", required=True)
    web.add_argument("--url", required=True)
    web.add_argument("--type", default="article", choices=[kind.value for kind in SourceType])
    web.add_argument("--allow-domain", action="append", default=[])
    web.add_argument("--language", default="und")
    crawl = commands.add_parser("crawl", help="Crawl explicit authorised domains, respecting robots.txt; no API key")
    crawl.add_argument("--subject", required=True)
    crawl.add_argument("--seed", action="append", required=True)
    crawl.add_argument("--allow-domain", action="append", required=True)
    crawl.add_argument("--type", default="article", choices=[kind.value for kind in SourceType])
    crawl.add_argument("--language", default="und")
    crawl.add_argument("--query", default="")
    crawl.add_argument("--max-pages", default=20, type=int)
    git = commands.add_parser("ingest-git", help="Ingest a local/exported Git repository")
    git.add_argument("--subject", required=True)
    git.add_argument("--path", required=True)
    git.add_argument("--language", default="und")
    analyze = commands.add_parser("analyze", help="Run all analytic lenses on stored evidence")
    analyze.add_argument("--subject", required=True)
    analyze.add_argument("--kinds", nargs="*", choices=[kind.value for kind in AnalysisKind])
    research = commands.add_parser("research", help="Search the local evidence RAG")
    research.add_argument("--query", required=True)
    research.add_argument("--subject")
    plan = commands.add_parser("plan-research", help="Generate a multilingual, auditable web research plan")
    plan.add_argument("--objective", required=True)
    plan.add_argument("--name", action="append", required=True)
    plan.add_argument("--language", action="append", default=["und"])
    plan.add_argument("--term", action="append", required=True)
    compare = commands.add_parser("compare", help="Compare documented analytical categories of two subjects")
    compare.add_argument("--left", required=True)
    compare.add_argument("--right", required=True)
    artifact = commands.add_parser("artifact", help="Generate an evidence-linked knowledge or operational artifact")
    artifact.add_argument("--kind", required=True, choices=["knowledge_base", "encyclopedia", "decision_tree", "prompt", "checklist", "playbook", "patterns"])
    artifact.add_argument("--subject", required=True)
    artifact.add_argument("--topic", default="innovation", help="Checklist discipline or playbook topic")
    artifact.add_argument("--rule-id", help="Optional rule ID for a rule-specific decision tree")
    rule = commands.add_parser("compile-rule", help="Compile a reviewed claim into a rule and SOP")
    rule.add_argument("--claim-id", required=True)
    rule.add_argument("--name", required=True)
    rule.add_argument("--trigger", required=True)
    rule.add_argument("--action", required=True)
    rule.add_argument("--domain", action="append", required=True)
    rule.add_argument("--exclude", action="append", default=[])
    rule.add_argument("--counter-evidence-reviewed", action="store_true")
    workflow = commands.add_parser("workflow", help="Evaluate a guarded decision/release workflow")
    workflow.add_argument("--impact", required=True, choices=["low", "medium", "high"])
    workflow.add_argument("--evidence", required=True, type=float)
    workflow.add_argument("--reversibility", required=True, choices=["low", "high"])
    workflow.add_argument("--security-reviewed", action="store_true")
    workflow.add_argument("--tests-passed", action="store_true")
    workflow.add_argument("--privacy-reviewed", action="store_true")
    workflow.add_argument("--rollback-ready", action="store_true")
    workflow.add_argument("--observability-ready", action="store_true")
    watch = commands.add_parser("watch-source", help="Register an authorised public source for incremental update checks")
    watch.add_argument("--subject", required=True)
    watch.add_argument("--url", required=True)
    watch.add_argument("--type", default="article", choices=[kind.value for kind in SourceType])
    watch.add_argument("--allow-domain", action="append", default=[])
    watch.add_argument("--language", default="und")
    commands.add_parser("check-updates", help="Check registered authorised sources and re-analyse changed content")
    server = commands.add_parser("serve", help="Run local HTTP API")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", default=8080, type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "self-test":
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(EFIOSSelfTest)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1
    app = EFIApplication(args.database)
    if args.command == "capabilities":
        print_json(app.capabilities())
    elif args.command == "demo":
        demo(app)
    elif args.command == "ingest-file":
        print_json(app.ingest_local_file(subject_id=args.subject, path=args.path, source_type=args.type, language=args.language))
    elif args.command == "ingest-url":
        print_json(app.ingest_url({"subject_id": args.subject, "url": args.url, "source_type": args.type, "allowed_domains": args.allow_domain, "language": args.language}))
    elif args.command == "crawl":
        print_json(app.crawl_sources({"subject_id": args.subject, "seed_urls": args.seed, "allowed_domains": args.allow_domain, "source_type": args.type, "language": args.language, "query": args.query, "max_pages": args.max_pages}))
    elif args.command == "ingest-git":
        evidence = LocalGitConnector().ingest(subject_id=args.subject, repository=args.path, language=args.language)
        print_json({"evidence": evidence.to_dict(), "agent_run": app.orchestrator.process(evidence).to_dict()})
    elif args.command == "analyze":
        print_json(app.analyze_subject(args.subject, args.kinds))
    elif args.command == "research":
        print_json(app.research(args.query, args.subject))
    elif args.command == "plan-research":
        print_json(app.plan_research({"objective": args.objective, "names": args.name, "languages": args.language, "topic_terms": args.term}))
    elif args.command == "compare":
        print_json(app.compare(args.left, args.right))
    elif args.command == "artifact":
        print_json(app.generate_artifact({"kind": args.kind, "subject_id": args.subject, "topic": args.topic, "rule_id": args.rule_id}))
    elif args.command == "compile-rule":
        print_json(app.compile_rule({"claim_id": args.claim_id, "name": args.name, "trigger": args.trigger, "action": args.action, "applicability": args.domain, "exclusions": args.exclude, "counter_evidence_reviewed": args.counter_evidence_reviewed}))
    elif args.command == "workflow":
        print_json(app.evaluate_workflow({"impact": args.impact, "evidence_strength": args.evidence, "reversibility": args.reversibility, "security_reviewed": args.security_reviewed, "tests_passed": args.tests_passed, "privacy_reviewed": args.privacy_reviewed, "rollback_ready": args.rollback_ready, "observability_ready": args.observability_ready}))
    elif args.command == "watch-source":
        print_json(app.register_update_source({"subject_id": args.subject, "url": args.url, "source_type": args.type, "allowed_domains": args.allow_domain, "language": args.language}))
    elif args.command == "check-updates":
        print_json(app.check_updates())
    elif args.command == "serve":
        server = build_server(app, args.host, args.port)
        print(f"{APP_NAME} listening at http://{args.host}:{args.port}  (Ctrl+C to stop)")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
