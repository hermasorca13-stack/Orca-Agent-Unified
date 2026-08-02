"""
skills/efi_os_skill.py — Thin Orca wrapper around the external EFI-OS tool.

EFI-OS is a single-file, stdlib-only Python tool that provides an
"Evidence-Driven Founder Intelligence Operating System": local
ingestion of interviews / papers / patents / Git repos, a local
SQLite-backed RAG, engineering analysis, decision workflows, and
gated releases. It uses NO external API keys — everything runs
locally.

This file is the only place in the Orca project that talks to
EFI-OS. It is a thin wrapper: it locates the bundled
`tools/EFI_OS.py` (verified by SHA-256 at import time), and shells
out to its CLI via subprocess. We deliberately do NOT re-implement
EFI-OS in Orca — the goal is "smart integration", not duplication.

Public surface:
- `EFIOSError` — single, user-friendly exception class.
- `EFI_PATH` — absolute path to the bundled tool, resolved at import.
- `EFI_SHA256` — verified SHA-256 fingerprint (must match the file).
- `run(subcommand, *args, timeout=...)` — invoke any EFI-OS subcommand,
  return (exit_code, stdout, stderr).
- `capabilities() -> dict` — the JSON capabilities matrix.
- `self_test() -> dict` — run the bundled self-tests; returns the
  summary {total, ok, failed, skipped}.
- `ingest_file(subject, path, type)` — shorthand for the CLI.
- `analyze(subject, kinds=None)` — shorthand.
- `research(query, ...)` — shorthand.
- `serve(port=8080)` — starts the local HTTP API in a background
  thread; returns the server thread (call .join() to wait, or just
  let the bot process own the lifecycle).

Engineering contract (Apple + Microsoft grade):
- Verify the bundled file exists + SHA-256 matches on import.
  Any drift raises EFIOSTamperedError so a malicious or corrupted
  file is caught before we ever invoke it.
- Lazy subprocess: we only spawn Python when an actual call is
  made, never on import. That keeps the Orca bot startup time
  unchanged for callers that never touch EFI-OS.
- Friendly error mapping for the common subprocess failures
  (missing binary, non-zero exit, timeout).
- loguru integration for telemetry.
- No globals mutated. Pure functional: every call constructs a
  fresh subprocess.

This file is ADD-ONLY. It does not modify any existing Orca module.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from loguru import logger


# ----------------------------------------------------------------------
# Constants — verified at import time
# ----------------------------------------------------------------------
# The bundled EFI-OS lives in tools/EFI_OS.py at the repo root.
# `__file__` is .../skills/efi_os_skill.py → parent.parent = repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
EFI_PATH = _REPO_ROOT / "tools" / "EFI_OS.py"

# SHA-256 fingerprint of the bundled file. This MUST match the file
# on disk; if it doesn't, we raise a tamper error and refuse to call
# the tool. Bump this constant when shipping a new EFI-OS release.
EFI_SHA256 = "abac459e74f23e1e7f796b899ec54af976fe07797923040a4d6b5fd65c5deace"

# Subcommand names. Kept here so callers don't have to remember them.
SUB_COMMANDS = (
    "self-test", "demo", "capabilities",
    "ingest-file", "ingest-url", "ingest-git",
    "analyze", "research", "compare",
    "add-rule", "run-workflow", "serve",
    "export",
)


class EFIOSTamperedError(RuntimeError):
    """Bundled EFI-OS file failed integrity check."""


class EFIOSError(RuntimeError):
    """Raised when an EFI-OS call fails for any reason."""


# ----------------------------------------------------------------------
# Integrity check at import
# ----------------------------------------------------------------------
def _verify_integrity() -> None:
    """Confirm the bundled EFI-OS exists and matches the SHA-256."""
    if not EFI_PATH.exists():
        raise EFIOSTamperedError(
            f"EFI-OS not found at {EFI_PATH}. "
            f"Expected the bundled tool/EFI_OS.py."
        )
    actual = hashlib.sha256(EFI_PATH.read_bytes()).hexdigest()
    if actual != EFI_SHA256:
        raise EFIOSTamperedError(
            f"EFI-OS SHA-256 mismatch.\n"
            f"  expected: {EFI_SHA256}\n"
            f"  actual:   {actual}\n"
            f"  file:     {EFI_PATH}\n"
            f"Refusing to run a tampered or out-of-date binary. "
            f"Update tools/EFI_OS.py and bump EFI_SHA256 in "
            f"skills/efi_os_skill.py."
        )


# Run the check at import time so any caller gets the safety net.
_verify_integrity()
logger.info("efi_os_skill loaded | path={} sha256=ok", EFI_PATH)


# ----------------------------------------------------------------------
# Internal subprocess helper
# ----------------------------------------------------------------------
def _run(
    subcommand: str,
    args: Optional[List[str]] = None,
    *,
    timeout: float = 60.0,
    cwd: Optional[Union[str, Path]] = None,
) -> Tuple[int, str, str]:
    """Invoke EFI-OS as a subprocess and return (rc, stdout, stderr).

    The Python interpreter used is the one currently running the
    Orca bot (sys.executable). This avoids version mismatches.
    """
    if subcommand not in SUB_COMMANDS:
        raise EFIOSError(
            f"Unknown EFI-OS subcommand {subcommand!r}. "
            f"Allowed: {list(SUB_COMMANDS)}"
        )
    cmd: List[str] = [sys.executable, str(EFI_PATH), subcommand]
    cmd.extend(args or [])

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd) if cwd else str(_REPO_ROOT),
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        raise EFIOSError(
            f"EFI-OS {subcommand} timed out after {timeout}s"
        ) from exc
    except FileNotFoundError as exc:
        raise EFIOSError(
            f"Could not launch EFI-OS: {exc}. "
            f"Check that {EFI_PATH} exists and that '{sys.executable}' "
            f"is on PATH."
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise EFIOSError(
            f"EFI-OS {subcommand} failed: {exc.__class__.__name__}: {exc}"
        ) from exc


def _run_json(subcommand: str, args: Optional[List[str]] = None,
              *, timeout: float = 60.0) -> Dict[str, Any]:
    """Invoke EFI-OS and parse stdout as JSON. Raises on parse failure."""
    rc, out, err = _run(subcommand, args, timeout=timeout)
    if rc != 0:
        # Surface the last useful line of stderr.
        msg = (err or out or "unknown error").strip().splitlines()
        tail = msg[-1] if msg else "unknown error"
        raise EFIOSError(f"EFI-OS {subcommand} returned {rc}: {tail}")
    # Tolerate leading/trailing non-JSON content (e.g. a warning line).
    text = out.strip()
    # Find the first '{' or '[' and parse from there.
    i_brace = text.find("{")
    i_brack = text.find("[")
    starts = [i for i in (i_brace, i_brack) if i != -1]
    if not starts:
        raise EFIOSError(
            f"EFI-OS {subcommand} returned no JSON: {text[:200]!r}"
        )
    start = min(starts)
    try:
        return json.loads(text[start:])
    except json.JSONDecodeError as exc:
        raise EFIOSError(
            f"EFI-OS {subcommand} returned malformed JSON: {exc}. "
            f"Head: {text[start:start+120]!r}"
        ) from exc


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------
def run(subcommand: str, *args: str, timeout: float = 60.0) -> Tuple[int, str, str]:
    """Low-level: invoke any EFI-OS subcommand and return (rc, stdout, stderr)."""
    return _run(subcommand, list(args), timeout=timeout)


def capabilities() -> Dict[str, Any]:
    """Return the EFI-OS capabilities matrix as a dict."""
    return _run_json("capabilities", timeout=15.0)


def self_test() -> Dict[str, Any]:
    """Run the bundled EFI-OS self-tests and return the summary.

    Returns a dict: {ok: int, failed: int, skipped: int, total: int,
    details: list of (test_name, status)}.
    """
    rc, out, err = _run("self-test", timeout=180.0)
    combined = (out or "") + "\n" + (err or "")
    # pytest -v output: "test_X (...) ... ok|FAIL|ERROR|skipped"
    pat = re.compile(r"(test_\w+)\s+\(([^)]+)\)\s+\.\.\.\s+(ok|FAIL|ERROR|skipped)")
    tests = pat.findall(combined)
    details = [{"name": n, "suite": s, "status": st} for n, s, st in tests]
    ok = sum(1 for t in details if t["status"] == "ok")
    failed = sum(1 for t in details if t["status"] in ("FAIL", "ERROR"))
    skipped = sum(1 for t in details if t["status"] == "skipped")
    return {
        "ok": ok, "failed": failed, "skipped": skipped,
        "total": len(details),
        "returncode": rc,
        "details": details,
    }


def ingest_file(subject: str, path: str, source_type: str,
                *, timeout: float = 60.0) -> Dict[str, Any]:
    """Ingest a local file as evidence. `source_type` matches EFI-OS SourceType."""
    return _run_json(
        "ingest-file",
        ["--subject", subject, "--path", path, "--type", source_type],
        timeout=timeout,
    )


def ingest_url(subject: str, url: str, source_type: str = "article",
               *, timeout: float = 60.0) -> Dict[str, Any]:
    """Ingest a public URL as evidence. (Public URL only — no login.)"""
    return _run_json(
        "ingest-url",
        ["--subject", subject, "--url", url, "--type", source_type],
        timeout=timeout,
    )


def ingest_git(subject: str, path: str, *, timeout: float = 120.0) -> Dict[str, Any]:
    """Ingest a LOCAL git repository (no network access)."""
    return _run_json(
        "ingest-git", ["--subject", subject, "--path", path], timeout=timeout,
    )


def analyze(subject: str, kinds: Optional[List[str]] = None,
            *, timeout: float = 120.0) -> Dict[str, Any]:
    """Run engineering analysis on a subject. `kinds` is optional list of
    AnalysisKind names; if None, EFI-OS picks the default set."""
    args = ["--subject", subject]
    if kinds:
        args.extend(["--kinds", ",".join(kinds)])
    return _run_json("analyze", args, timeout=timeout)


def research(query: str, *, subject: Optional[str] = None,
             timeout: float = 60.0) -> Dict[str, Any]:
    """Run a local RAG research query."""
    args = ["--query", query]
    if subject:
        args.extend(["--subject", subject])
    return _run_json("research", args, timeout=timeout)


def compare(subjects: List[str], *, timeout: float = 60.0) -> Dict[str, Any]:
    """Compare two or more subjects and rank shared / different principles."""
    if len(subjects) < 2:
        raise EFIOSError("compare needs at least 2 subjects")
    return _run_json("compare", ["--subjects", ",".join(subjects)], timeout=timeout)


def add_rule(claim_id: str, *, name: str, trigger: str, action: str,
             applicability: Optional[List[str]] = None,
             exclusions: Optional[List[str]] = None,
             counter_evidence_reviewed: bool = False,
             timeout: float = 30.0) -> Dict[str, Any]:
    """Compile a new operational rule from a claim."""
    args = [
        "--claim", claim_id,
        "--name", name,
        "--trigger", trigger,
        "--action", action,
    ]
    if applicability:
        args.extend(["--applicability", ",".join(applicability)])
    if exclusions:
        args.extend(["--exclusions", ",".join(exclusions)])
    if counter_evidence_reviewed:
        args.append("--counter-evidence-reviewed")
    return _run_json("add-rule", args, timeout=timeout)


def run_workflow(workflow: str, *, evidence: Optional[List[str]] = None,
                 timeout: float = 60.0) -> Dict[str, Any]:
    """Run a decision workflow. `workflow` is the workflow name."""
    args = ["--workflow", workflow]
    if evidence:
        args.extend(["--evidence", ",".join(evidence)])
    return _run_json("run-workflow", args, timeout=timeout)


# ----------------------------------------------------------------------
# HTTP serve (background thread)
# ----------------------------------------------------------------------
class _ServerThread(threading.Thread):
    """Run `python EFI_OS.py serve --port N` in a background thread."""

    def __init__(self, port: int, timeout: float = 15.0):
        super().__init__(daemon=True, name=f"efi-serve-{port}")
        self.port = port
        self.timeout = timeout
        self._rc: Optional[int] = None
        self._out: str = ""
        self._err: str = ""
        self._exc: Optional[BaseException] = None

    def run(self) -> None:
        try:
            proc = subprocess.run(
                [sys.executable, str(EFI_PATH), "serve", "--port", str(self.port)],
                capture_output=True, text=True,
                timeout=self.timeout,
                cwd=str(_REPO_ROOT),
            )
            self._rc = proc.returncode
            self._out = proc.stdout
            self._err = proc.stderr
        except BaseException as exc:  # noqa: BLE001
            self._exc = exc

    @property
    def exit_code(self) -> Optional[int]:
        return self._rc

    @property
    def stdout(self) -> str:
        return self._out

    @property
    def stderr(self) -> str:
        return self._err

    @property
    def exception(self) -> Optional[BaseException]:
        return self._exc


def serve(port: int = 8080, *, timeout: float = 15.0) -> _ServerThread:
    """Start the local EFI-OS HTTP API in a background thread.

    The thread is daemonised, so it dies with the Orca bot process.
    Returns the thread (call .join(timeout) to wait, or read
    .exit_code / .stdout / .stderr after).
    """
    t = _ServerThread(port=port, timeout=timeout)
    t.start()
    logger.info("efi_os_skill serve started on port {} (pid alive={})",
                port, t.is_alive())
    return t


# ----------------------------------------------------------------------
# Format helper (Telegram-friendly)
# ----------------------------------------------------------------------
def format_capabilities(cap: Dict[str, Any]) -> str:
    """Format the capabilities matrix as a compact Telegram card."""
    lines = [f"🛠 *EFI-OS — capabilities ({cap.get('service', '?')})*",
            f"_single_file: {cap.get('single_file')}  •  "
            f"keys required: {cap.get('external_api_keys_required')}_",
            ""]
    caps = cap.get("capabilities") or {}
    for i, (k, v) in enumerate(caps.items(), 1):
        lines.append(f"`{i:02d}` *{k}*\n     _{v}_")
    return "\n".join(lines)


__all__ = [
    "EFIOSError", "EFIOSTamperedError",
    "EFI_PATH", "EFI_SHA256",
    "SUB_COMMANDS",
    "run", "capabilities", "self_test",
    "ingest_file", "ingest_url", "ingest_git",
    "analyze", "research", "compare",
    "add_rule", "run_workflow",
    "serve", "format_capabilities",
]
