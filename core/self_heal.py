"""
core/self_heal.py — Watchdog & self-healing for Orca Agent.

Provides:
  - SelfHeal: background task that probes (DB, FS, Telegram) every N seconds
    and auto-recovers from transient failures.
  - /diag command: full diagnostic dump for Telegram replies.

Healing actions (add-only, non-destructive):
  - DB:    if journal_mode != 'wal', re-enable WAL on next call.
  - FS:    if data/ or logs/ missing, recreate.
  - Network: if Telegram getMe fails 3x in a row, log + alert (no auto-relogin
    because the bot token is server-side; we just surface the error).
  - Process: if a heartbeat file is older than HEARTBEAT_STALE_SEC, the bot
    is considered stuck. We touch the file from the main loop.

This module never deletes user data. It only ENABLES missing infrastructure.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger


HEARTBEAT_STALE_SEC = int(os.getenv("HEARTBEAT_STALE_SEC", "120"))
PROBE_INTERVAL_SEC = int(os.getenv("SELF_HEAL_INTERVAL", "60"))


@dataclass
class ProbeReport:
    db_ok: bool = True
    db_journal: str = "unknown"
    fs_ok: bool = True
    fs_missing: list = field(default_factory=list)
    network_ok: bool = True
    network_err: str = ""
    heartbeat_ok: bool = True
    heartbeat_age_sec: int = 0
    uptime_sec: float = 0.0
    last_action: str = "none"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "db_ok": self.db_ok,
            "db_journal": self.db_journal,
            "fs_ok": self.fs_ok,
            "fs_missing": self.fs_missing,
            "network_ok": self.network_ok,
            "network_err": self.network_err,
            "heartbeat_ok": self.heartbeat_ok,
            "heartbeat_age_sec": self.heartbeat_age_sec,
            "uptime_sec": round(self.uptime_sec, 1),
            "last_action": self.last_action,
        }

    def format_telegram(self) -> str:
        ok = lambda b: "✅" if b else "❌"
        lines = [
            f"{ok(self.db_ok)} DB  ({self.db_journal})",
            f"{ok(self.fs_ok)} FS  missing={self.fs_missing}",
            f"{ok(self.network_ok)} Net {self.network_err or ''}",
            f"{ok(self.heartbeat_ok)} Heartbeat ({self.heartbeat_age_sec}s old)",
            f"⏱  Uptime: {self.uptime_sec:.0f}s",
            f"🛠  Last action: {self.last_action}",
        ]
        return "\n".join(lines)


class SelfHeal:
    def __init__(self, root: Path, db_path: Path, telegram_token: str = ""):
        self.root = Path(root)
        self.db_path = Path(db_path)
        self.telegram_token = telegram_token
        self._start = time.monotonic()
        self._task: Optional[asyncio.Task] = None
        self._last_report = ProbeReport()
        self._consecutive_net_failures = 0

    # -- probe paths ---------------------------------------------------------
    def _probe_db(self) -> tuple[bool, str]:
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.db_path), timeout=5)
            try:
                mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
                if mode.lower() != "wal":
                    try:
                        conn.execute("PRAGMA journal_mode=WAL")
                        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
                    except Exception as e:
                        logger.warning(f"Could not enable WAL: {e}")
                return True, mode
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"DB probe failed: {e}")
            return False, f"error: {e}"

    def _probe_fs(self) -> tuple[bool, list]:
        missing = []
        for sub in ("data", "logs", "backups"):
            p = self.root / sub
            if not p.exists():
                try:
                    p.mkdir(parents=True, exist_ok=True)
                    missing.append(sub)  # was missing, now healed
                except Exception as e:
                    missing.append(f"{sub}(err:{e})")
                    return False, missing
        return True, missing

    def _probe_heartbeat(self) -> tuple[bool, int]:
        hb = self.root / "data" / "heartbeat"
        if not hb.exists():
            hb.parent.mkdir(parents=True, exist_ok=True)
            hb.write_text(str(time.time()))
            return True, 0
        try:
            ts = float(hb.read_text().strip())
            age = int(time.time() - ts)
            return age < HEARTBEAT_STALE_SEC, age
        except Exception:
            return False, -1

    async def _probe_network(self) -> tuple[bool, str]:
        if not self.telegram_token:
            return True, "no-token"
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(
                    f"https://api.telegram.org/bot{self.telegram_token}/getMe"
                )
                ok = r.status_code == 200 and r.json().get("ok") is True
                return ok, "" if ok else f"http={r.status_code}"
        except Exception as e:
            return False, str(e)[:80]

    def touch_heartbeat(self):
        try:
            hb = self.root / "data" / "heartbeat"
            hb.parent.mkdir(parents=True, exist_ok=True)
            hb.write_text(str(time.time()))
        except Exception:
            pass

    # -- main loop -----------------------------------------------------------
    async def _loop(self):
        logger.info(f"SelfHeal loop started (interval={PROBE_INTERVAL_SEC}s)")
        while True:
            try:
                await self._run_once()
            except Exception as e:
                logger.exception(f"SelfHeal iteration crashed: {e}")
            await asyncio.sleep(PROBE_INTERVAL_SEC)

    async def _run_once(self):
        db_ok, journal = self._probe_db()
        fs_ok, missing = self._probe_fs()
        hb_ok, hb_age = self._probe_heartbeat()
        net_ok, net_err = await self._probe_network()
        if net_ok:
            self._consecutive_net_failures = 0
        else:
            self._consecutive_net_failures += 1

        action = "none"
        if not db_ok:
            action = "recreate-db"
        elif missing:
            action = f"recreated: {missing}"
        elif self._consecutive_net_failures >= 3:
            action = f"net-down-{self._consecutive_net_failures}x"
        elif not hb_ok:
            action = "stale-heartbeat"

        self._last_report = ProbeReport(
            db_ok=db_ok, db_journal=journal,
            fs_ok=fs_ok, fs_missing=missing,
            network_ok=net_ok, network_err=net_err,
            heartbeat_ok=hb_ok, heartbeat_age_sec=hb_age,
            uptime_sec=time.monotonic() - self._start,
            last_action=action,
        )

    # -- lifecycle -----------------------------------------------------------
    def start(self):
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop(), name="self-heal")

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    # -- /diag ---------------------------------------------------------------
    def diag(self) -> ProbeReport:
        # synchronous refresh for command replies
        db_ok, journal = self._probe_db()
        fs_ok, missing = self._probe_fs()
        hb_ok, hb_age = self._probe_heartbeat()
        # network probe is async — return last cached value
        self._last_report.db_ok = db_ok
        self._last_report.db_journal = journal
        self._last_report.fs_ok = fs_ok
        self._last_report.fs_missing = missing
        self._last_report.heartbeat_ok = hb_ok
        self._last_report.heartbeat_age_sec = hb_age
        self._last_report.uptime_sec = time.monotonic() - self._start
        return self._last_report
