# github_sync/gh_sync.py - Real GitHub Sync (Single Source)
"""
Pushes local files to GitHub using Contents API.
Falls back to local git commit if no GITHUB_TOKEN.
"""
import base64
import json
import time
import urllib.request
import urllib.error
import subprocess
from pathlib import Path
from loguru import logger
from core.config import config

API = "https://api.github.com"

def _req(path, method="GET", body=None, token=None):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "OrcaAgent/1.0",
    }
    if token:
        headers["Authorization"] = f"token {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{API}{path}", data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")
    except Exception as e:
        return 0, {"error": str(e)}

def _collect(root: Path) -> dict[str, str]:
    """Return {relative_path: base64_content} for every file under root."""
    skip = {".git", "__pycache__", "logs", "backups", "data", "node_modules", ".venv", "venv"}
    out = {}
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(s in p.parts for s in skip):
            continue
        rel = p.relative_to(root).as_posix()
        if rel == ".env" or rel.startswith(".env."):
            continue
        try:
            content = p.read_bytes()
            if len(content) > 5_000_000:  # 5MB limit per file
                continue
            out[rel] = base64.b64encode(content).decode()
        except Exception as e:
            logger.warning(f"skip {rel}: {e}")
    return out

def sync_to_github() -> dict:
    root = config.ROOT
    token = config.GH_TOKEN
    repo = config.GH_REPO
    branch = config.GH_BRANCH

    if not token:
        return _local_git(root)

    files = _collect(root)
    logger.info(f"Pushing {len(files)} files to {config.GH_USER}/{repo}@{branch}")

    code, info = _req(f"/repos/{config.GH_USER}/{repo}", token=token)
    if code != 200:
        return {"ok": False, "msg": f"repo access {code}: {info}"}

    code, ref = _req(f"/repos/{config.GH_USER}/{repo}/git/ref/heads/{branch}", token=token)
    if code != 200:
        return {"ok": False, "msg": f"branch ref {code}: {ref}"}

    pushed = failed = 0
    for rel, b64 in files.items():
        # check existing
        c, existing = _req(f"/repos/{config.GH_USER}/{repo}/contents/{rel}?ref={branch}", token=token)
        body = {"message": f"sync: {rel}", "content": b64, "branch": branch}
        if c == 200 and "sha" in existing:
            body["sha"] = existing["sha"]
        sc, _ = _req(f"/repos/{config.GH_USER}/{repo}/contents/{rel}", method="PUT", body=body, token=token)
        if sc in (200, 201):
            pushed += 1
        else:
            failed += 1
        time.sleep(0.05)

    return {"ok": failed == 0, "msg": f"pushed {pushed}, failed {failed}, total {len(files)}"}

def _local_git(root: Path) -> dict:
    try:
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "orca sync"], cwd=root, check=True, capture_output=True)
        return {"ok": True, "msg": f"local commit done (no GITHUB_TOKEN)"}
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode() if e.stderr else str(e)
        return {"ok": False, "msg": f"git error: {err}"}
