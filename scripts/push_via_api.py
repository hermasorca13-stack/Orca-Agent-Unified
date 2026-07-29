#!/usr/bin/env python3
"""
scripts/push_via_api.py — Push local commits to GitHub via Contents/Data API.
Use this only when the PAT lacks git push scope. It uploads a single commit
containing the current local HEAD's tree.

Usage:
  python3 scripts/push_via_api.py
"""
import os
import sys
import json
import base64
import urllib.request
import urllib.error
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

GH_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GH_USER = os.getenv("GITHUB_USERNAME", "").strip()
GH_REPO = os.getenv("GITHUB_REPO", "").strip()
BRANCH = os.getenv("GITHUB_BRANCH", "master").strip()

if not GH_TOKEN or not GH_USER or not GH_REPO:
    print("❌ Missing GITHUB_TOKEN / GITHUB_USERNAME / GITHUB_REPO in .env")
    sys.exit(1)

API = "https://api.github.com"
HEADERS = {
    "Authorization": f"Bearer {GH_TOKEN}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "OrcaAgent-Push/1.0",
    "X-GitHub-Api-Version": "2022-11-28",
}


def gh(path, method="GET", body=None):
    url = f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="ignore")
        print(f"❌ {method} {path} → {e.code}: {body_text[:500]}")
        raise


def main():
    print(f"🐋 ORCA PUSH via API")
    print(f"   user={GH_USER} repo={GH_REPO} branch={BRANCH}")

    # 1) Get current branch ref
    ref = gh(f"/repos/{GH_USER}/{GH_REPO}/git/ref/heads/{BRANCH}")
    parent_sha = ref["object"]["sha"]
    print(f"   parent={parent_sha[:10]}")

    # 2) Get parent commit
    parent = gh(f"/repos/{GH_USER}/{GH_REPO}/git/commits/{parent_sha}")
    base_tree = parent["tree"]["sha"]
    print(f"   base_tree={base_tree[:10]}")

    # 3) Build tree of all files in working dir (skip .git, data/, logs/, __pycache__)
    files = []
    skip_dirs = {".git", "data", "logs", "__pycache__", ".pytest_cache", "backups", "faiss_index", ".index", ".github", "node_modules", ".idea", ".vscode"}
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT).as_posix()
        if any(part in skip_dirs for part in rel.split("/")):
            continue
        # Allow .env to be skipped (secrets)
        if rel in {".env", "bot.log"} or rel.endswith(".db") or rel.endswith(".sqlite3"):
            continue
        with open(p, "rb") as f:
            content = base64.b64encode(f.read()).decode()
        files.append({"path": rel, "mode": "100644", "type": "blob", "content": content})

    print(f"   uploading {len(files)} files…")
    if not files:
        print("   nothing to push")
        return

    # 4) Create tree
    tree = gh(
        f"/repos/{GH_USER}/{GH_REPO}/git/trees",
        method="POST",
        body={"base_tree": base_tree, "tree": files},
    )
    new_tree_sha = tree["sha"]
    print(f"   new_tree={new_tree_sha[:10]}")

    # 5) Get local commit message
    try:
        msg = subprocess.check_output(
            ["git", "-C", str(ROOT), "log", "-1", "--format=%s"],
            stderr=subprocess.DEVNULL,
        ).decode().strip() or "chore: push via API"
    except Exception:
        msg = "chore: push via API"

    # 6) Create commit
    commit = gh(
        f"/repos/{GH_USER}/{GH_REPO}/git/commits",
        method="POST",
        body={"message": msg, "tree": new_tree_sha, "parents": [parent_sha]},
    )
    new_commit_sha = commit["sha"]
    print(f"   new_commit={new_commit_sha[:10]}")

    # 7) Update ref
    gh(
        f"/repos/{GH_USER}/{GH_REPO}/git/refs/heads/{BRANCH}",
        method="PATCH",
        body={"sha": new_commit_sha, "force": False},
    )
    print(f"   ✅ pushed to {BRANCH}")


if __name__ == "__main__":
    main()
