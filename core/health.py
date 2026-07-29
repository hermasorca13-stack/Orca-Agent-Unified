"""
core/health.py — Lightweight health/readiness probe for Orca Agent.

Why this file:
- Operators (and Telegram uptime checks) need a single endpoint that says
  "yes the bot can talk to its DB, FS, and outbound network".
- We deliberately keep it dependency-free: stdlib only, no FastAPI, no
  extra ports to manage. The launcher can poll this via the existing
  Python process.

What it does:
- `probe()` returns a dict with status, db_ok, fs_ok, net_ok, version, ts.
- `format_for_telegram(probe)` turns that dict into a MarkdownV2-friendly
  string that fits in a single Telegram reply.

How to use from a handler:
    from core.health import probe, format_for_telegram
    p = probe()
    await update.message.reply_text(format_for_telegram(p), parse_mode="MarkdownV2")

This file is ADD-ONLY. It does not touch any existing module.
"""
from __future__ import annotations

import os
import socket
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict

# Repo root resolved relative to this file.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_DB_PATH = _REPO_ROOT / "data" / "orca_memory.db"
_VERSION = "0.6.0"  # bumped in lockstep with BUILD_HISTORY


def _check_db() -> bool:
    """Try a cheap PRAGMA on the memory DB. Returns True if reachable."""
    try:
        if not _DB_PATH.exists():
            return False
        # Open read-only with a 2s timeout so a locked DB never blocks.
        con = sqlite3.connect(f"file:{_DB_PATH}?mode=ro", uri=True, timeout=2.0)
        try:
            cur = con.execute("PRAGMA quick_check;")
            row = cur.fetchone()
            return bool(row and row[0] == "ok")
        finally:
            con.close()
    except Exception:
        return False


def _check_fs() -> bool:
    """Repo root must be writable."""
    try:
        probe = _REPO_ROOT / ".health_probe"
        probe.write_text(str(time.time()))
        probe.unlink()
        return True
    except Exception:
        return False


def _check_net() -> bool:
    """Can we resolve api.telegram.org? (DNS only — no traffic)"""
    try:
        socket.getaddrinfo("api.telegram.org", 443, type=socket.SOCK_STREAM)
        return True
    except Exception:
        return False


def probe() -> Dict[str, Any]:
    """Aggregate probe. Safe to call from any context."""
    db_ok = _check_db()
    fs_ok = _check_fs()
    net_ok = _check_net()
    overall = "ok" if (db_ok and fs_ok and net_ok) else "degraded"
    return {
        "status": overall,
        "version": _VERSION,
        "db_ok": db_ok,
        "fs_ok": fs_ok,
        "net_ok": net_ok,
        "ts": int(time.time()),
        "db_path": str(_DB_PATH.relative_to(_REPO_ROOT)) if _DB_PATH.exists() else None,
    }


# Telegram MarkdownV2 reserves these characters; escape them in user text.
_MDV2_SPECIAL = r"_*[]()~`>#+-=|{}.!\\"


def _mdv2_escape(text: str) -> str:
    out = []
    for ch in text:
        if ch in _MDV2_SPECIAL:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def format_for_telegram(p: Dict[str, Any]) -> str:
    """Render a probe dict as a MarkdownV2-safe status card."""
    icon = "🟢" if p["status"] == "ok" else "🟡"
    lines = [
        f"{icon} *Orca Health*  v{_mdv2_escape(p['version'])}",
        "",
        f"Status: *{_mdv2_escape(p['status'].upper())}*",
        f"DB:     {'✅' if p['db_ok'] else '❌'}",
        f"FS:     {'✅' if p['fs_ok'] else '❌'}",
        f"Net:    {'✅' if p['net_ok'] else '❌'}",
    ]
    if p.get("db_path"):
        lines.append(f"Path:   `{_mdv2_escape(p['db_path'])}`")
    return "\n".join(lines)
