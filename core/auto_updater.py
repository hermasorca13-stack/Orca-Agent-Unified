"""
core/auto_updater.py — Self-update mechanism for Orca Agent.

When a new push happens on the configured GitHub branch, the running bot can
detect the change (via ETag polling) and pull the latest code. This lets the
production instance stay in sync without manual redeploys.

This is an ADDITION to the existing github_sync module — it does not replace
it. The sync module is for pushing local changes upstream; this module is for
pulling remote changes into the running bot.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

import urllib.request

from core.config import config
from loguru import logger


_API = "https://api.github.com"
_BRANCH_ETAG: dict[str, str] = {}


def _gh_headers(token: str) -> dict:
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "OrcaAgent-AutoUpdater/1.0",
    }
    if token:
        h["Authorization"] = f"token {token}"
    return h


def check_remote_sha() -> Optional[str]:
    """Return the current commit SHA on the configured branch, or None on error.

    Uses an ETag cache so we don't hammer the GitHub API — only one network
    request per call. The HTTP 304 short-circuit is the caller's job.
    """
    repo = config.GH_REPO
    branch = config.GH_BRANCH
    token = config.GH_TOKEN
    if not repo or not branch:
        return None
    url = f"{_API}/repos/hermasorca13-stack/{repo}/branches/{branch}"
    req = urllib.request.Request(url, headers=_gh_headers(token))
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            etag = r.headers.get("ETag", "")
            _BRANCH_ETAG[branch] = etag
            import json
            data = json.loads(r.read())
            return data.get("commit", {}).get("sha")
    except Exception as e:
        logger.debug(f"check_remote_sha failed: {e}")
        return None


def remote_changed(local_sha: str) -> bool:
    """Return True if the remote SHA differs from the locally known one."""
    remote = check_remote_sha()
    if not remote:
        return False
    return remote != local_sha


def get_local_sha() -> str:
    """Return the SHA of HEAD on the local clone (or empty string if no .git)."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(config.ROOT),
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return out.decode().strip()
    except Exception:
        return ""


def pull_latest() -> dict:
    """Run `git pull --ff-only` on the configured branch.

    Returns {ok, msg, before, after}.
    """
    before = get_local_sha()
    try:
        out = subprocess.check_output(
            ["git", "pull", "--ff-only", "origin", config.GH_BRANCH],
            cwd=str(config.ROOT),
            stderr=subprocess.STDOUT,
            timeout=60,
        )
        after = get_local_sha()
        msg = out.decode().strip()
        logger.info(f"auto-update pulled: {before[:7]} -> {after[:7]}")
        return {"ok": True, "msg": msg, "before": before, "after": after}
    except subprocess.CalledProcessError as e:
        return {"ok": False, "msg": e.output.decode() if e.output else str(e),
                "before": before, "after": before}
    except Exception as e:
        return {"ok": False, "msg": str(e), "before": before, "after": before}


def maybe_auto_update() -> dict:
    """Check remote and pull if changed. Safe to call on every /start.

    Returns {ok, changed, msg, before, after}.
    """
    local = get_local_sha()
    remote = check_remote_sha()
    if not remote:
        return {"ok": False, "changed": False, "msg": "remote check failed",
                "before": local, "after": local}
    if remote == local:
        return {"ok": True, "changed": False, "msg": "up-to-date",
                "before": local, "after": local}
    return {**pull_latest(), "changed": True}


def restart_bot() -> None:
    """Replace the current process with `python orca.py bot` so the new code
    takes over the long-polling slot. This is a clean, single-instance restart."""
    import sys
    orca_py = config.ROOT / "orca.py"
    if not orca_py.exists():
        logger.error("orca.py not found, cannot restart")
        return
    logger.info("auto-update: restarting bot via execvp")
    os.execvp(sys.executable, [sys.executable, str(orca_py), "bot"])
