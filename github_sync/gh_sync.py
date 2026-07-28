# github_sync/gh_sync.py - Real GitHub Sync via REST API
"""
Pushes local project files to GitHub repo Orca-Agent-Unified using the
GitHub Contents API. Falls back to local git if no token.
"""
import base64
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from loguru import logger
from core.config import config

API = "https://api.github.com"

def _req(path, method="GET", body=None, token=None):
    url = f"{API}{path}"
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "OrcaAgent/1.0"}
    if token:
        headers["Authorization"] = f"token {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")
    except Exception as e:
        return 0, {"error": str(e)}

def _collect_files(root: Path):
    files = {}
    skip = {".git", "__pycache__", ".env", "logs", "backups", "data", "node_modules"}
    for p in root.rglob("*"):
        if p.is_file() and not any(s in p.parts for s in skip):
            rel = p.relative_to(root).as_posix()
            if rel.startswith(".env"):
                continue
            try:
                content = p.read_bytes()
                if len(content) > 5_000_000:
                    continue
                files[rel] = base64.b64encode(content).decode()
            except Exception as e:
                logger.warning(f"skip {rel}: {e}")
    return files

def sync_to_github():
    root = config.ROOT
    token = config.GH_TOKEN
    repo = config.GH_REPO
    branch = config.GH_BRANCH

    if not token:
        # local git fallback
        return _local_git_sync(root, repo)

    files = _collect_files(root)
    logger.info(f"Uploading {len(files)} files to {repo}@{branch}")

    # Get repo info / default branch SHA
    code, repo_info = _req(f"/repos/{config.GH_USER}/{repo}", token=token)
    if code != 200:
        return {"ok": False, "msg": f"Repo access failed: {code} {repo_info}"}

    # Get ref SHA
    code, ref = _req(f"/repos/{config.GH_USER}/{repo}/git/ref/heads/{branch}", token=token)
    if code != 200:
        return {"ok": False, "msg": f"Branch ref failed: {code} {ref}"}
    base_sha = ref["object"]["sha"]

    # For each file: get sha if exists, then create/update
    pushed = 0
    failed = 0
    for rel, b64 in files.items():
        code, existing = _req(f"/repos/{config.GH_USER}/{repo}/contents/{rel}?ref={branch}", token=token)
        body = {
            "message": f"sync: {rel}",
            "content": b64,
            "branch": branch,
        }
        if code == 200 and "sha" in existing:
            body["sha"] = existing["sha"]
        c, r = _req(f"/repos/{config.GH_USER}/{repo}/contents/{rel}", method="PUT", body=body, token=token)
        if c in (200, 201):
            pushed += 1
        else:
            failed += 1
            logger.error(f"push {rel}: {c} {r}")
        time.sleep(0.05)

    return {"ok": failed == 0, "msg": f"pushed {pushed}, failed {failed}, total {len(files)}"}

def _local_git_sync(root: Path, repo: str):
    import subprocess
    try:
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "orca sync"], cwd=root, check=True, capture_output=True)
        return {"ok": True, "msg": f"local commit done (no GITHUB_TOKEN). Repo: {repo}"}
    except subprocess.CalledProcessError as e:
        return {"ok": False, "msg": f"git error: {e.stderr.decode() if e.stderr else e}"}
