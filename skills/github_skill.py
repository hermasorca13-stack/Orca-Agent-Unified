# skills/github_skill.py — GitHub Skill (PyGithub-backed)
"""
Full GitHub operations using PyGithub (official GitHub API wrapper, 7.7k+ stars).
Exposes a clean async-friendly facade for the Orca agent.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from loguru import logger
from github import Github, GithubException, Auth
from core.config import config

_NAME = "github"
_DESCRIPTION = "Full GitHub operations via PyGithub: repos, issues, PRs, releases, branches, gists, search, comments, labels, milestones."
_VERSION = "2.0.0"

_client: Optional[Github] = None


def _gh() -> Github:
    global _client
    if _client is None:
        if not config.GH_TOKEN:
            raise RuntimeError("GITHUB_TOKEN not configured")
        _client = Github(auth=Auth.Token(config.GH_TOKEN), per_page=30)
    return _client


# ---------- repo ----------
def get_repo(full_name: Optional[str] = None) -> Dict[str, Any]:
    full_name = full_name or config.GH_FULL_NAME
    r = _gh().get_repo(full_name)
    return {
        "name": r.full_name,
        "description": r.description,
        "stars": r.stargazers_count,
        "forks": r.forks_count,
        "open_issues": r.open_issues_count,
        "default_branch": r.default_branch,
        "private": r.private,
        "html_url": r.html_url,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "pushed_at": r.pushed_at.isoformat() if r.pushed_at else None,
    }


def list_repos(user: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    u = _gh().get_user(user or config.GH_USER)
    out = []
    for r in u.get_repos()[:limit]:
        out.append({
            "name": r.full_name,
            "private": r.private,
            "stars": r.stargazers_count,
            "forks": r.forks_count,
            "url": r.html_url,
        })
    return out


def create_repo(name: str, description: str = "", private: bool = False) -> Dict[str, Any]:
    u = _gh().get_user()
    r = u.create_repo(name=name, description=description, private=private, auto_init=True)
    return {"name": r.full_name, "url": r.html_url, "private": r.private}


def search_repos(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    res = _gh().search_repositories(query=query)
    return [{
        "name": r.full_name,
        "stars": r.stargazers_count,
        "description": r.description,
        "url": r.html_url,
    } for r in res[:limit]]


# ---------- issues ----------
def list_issues(state: str = "open", limit: int = 20, full_name: Optional[str] = None) -> List[Dict[str, Any]]:
    r = _gh().get_repo(full_name or config.GH_FULL_NAME)
    return [{
        "number": i.number,
        "title": i.title,
        "state": i.state,
        "user": i.user.login if i.user else None,
        "created_at": i.created_at.isoformat() if i.created_at else None,
        "labels": [l.name for l in i.labels],
        "url": i.html_url,
    } for i in r.get_issues(state=state)[:limit]]


def create_issue(title: str, body: str = "", labels: Optional[List[str]] = None,
                 full_name: Optional[str] = None) -> Dict[str, Any]:
    r = _gh().get_repo(full_name or config.GH_FULL_NAME)
    i = r.create_issue(title=title, body=body, labels=labels or [])
    return {"number": i.number, "url": i.html_url, "title": i.title}


def close_issue(number: int, full_name: Optional[str] = None) -> Dict[str, Any]:
    r = _gh().get_repo(full_name or config.GH_FULL_NAME)
    i = r.get_issue(number)
    i.edit(state="closed")
    return {"number": i.number, "state": i.state}


def comment_issue(number: int, body: str, full_name: Optional[str] = None) -> Dict[str, Any]:
    r = _gh().get_repo(full_name or config.GH_FULL_NAME)
    i = r.get_issue(number)
    c = i.create_comment(body)
    return {"id": c.id, "url": c.html_url}


# ---------- pull requests ----------
def list_prs(state: str = "open", limit: int = 20, full_name: Optional[str] = None) -> List[Dict[str, Any]]:
    r = _gh().get_repo(full_name or config.GH_FULL_NAME)
    return [{
        "number": p.number,
        "title": p.title,
        "state": p.state,
        "user": p.user.login if p.user else None,
        "merged": p.merged,
        "url": p.html_url,
    } for p in r.get_pulls(state=state)[:limit]]


def create_pr(title: str, head: str, base: str = "main", body: str = "",
              full_name: Optional[str] = None) -> Dict[str, Any]:
    r = _gh().get_repo(full_name or config.GH_FULL_NAME)
    p = r.create_pull(title=title, body=body, head=head, base=base)
    return {"number": p.number, "url": p.html_url, "title": p.title}


# ---------- releases ----------
def list_releases(limit: int = 10, full_name: Optional[str] = None) -> List[Dict[str, Any]]:
    r = _gh().get_repo(full_name or config.GH_FULL_NAME)
    out = []
    for rel in r.get_releases():
        if len(out) >= limit:
            break
        out.append({
            "tag": rel.tag_name,
            "name": rel.title,
            "published_at": rel.published_at.isoformat() if rel.published_at else None,
            "url": rel.html_url,
            "prerelease": rel.prerelease,
        })
    return out


def create_release(tag: str, name: str, body: str = "", draft: bool = False,
                   full_name: Optional[str] = None) -> Dict[str, Any]:
    r = _gh().get_repo(full_name or config.GH_FULL_NAME)
    rel = r.create_git_release(tag=tag, name=name, message=body, draft=draft)
    return {"tag": rel.tag_name, "url": rel.html_url}


# ---------- branches / tags ----------
def list_branches(full_name: Optional[str] = None) -> List[Dict[str, Any]]:
    r = _gh().get_repo(full_name or config.GH_FULL_NAME)
    return [{"name": b.name, "protected": b.protected} for b in r.get_branches()]


def create_branch(branch: str, from_branch: str = "main", full_name: Optional[str] = None) -> Dict[str, Any]:
    r = _gh().get_repo(full_name or config.GH_FULL_NAME)
    src = r.get_branch(from_branch)
    r.create_git_ref(ref=f"refs/heads/{branch}", sha=src.commit.sha)
    return {"branch": branch, "from": from_branch}


# ---------- contents ----------
def get_file(path: str, ref: str = "main", full_name: Optional[str] = None) -> Dict[str, Any]:
    r = _gh().get_repo(full_name or config.GH_FULL_NAME)
    try:
        c = r.get_contents(path, ref=ref)
        if isinstance(c, list):
            return {"type": "dir", "items": [x.path for x in c]}
        return {"type": "file", "path": c.path, "size": c.size, "decoded": c.decoded_content.decode("utf-8", errors="replace")}
    except GithubException as e:
        return {"error": str(e)}


def create_or_update_file(path: str, content: str, message: str, branch: str = "main",
                          full_name: Optional[str] = None) -> Dict[str, Any]:
    r = _gh().get_repo(full_name or config.GH_FULL_NAME)
    sha = None
    try:
        existing = r.get_contents(path, ref=branch)
        if not isinstance(existing, list):
            sha = existing.sha
    except GithubException:
        pass
    res = r.update_file(path=path, message=message, content=content, sha=sha, branch=branch)
    return {"commit": res["commit"].sha, "url": res["content"].html_url}


# ---------- search ----------
def search_code(query: str, full_name: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    q = f"{query} repo:{full_name or f'{config.GH_USER}/{config.GH_REPO}'}"
    res = _gh().search_code(query=q)
    return [{
        "name": c.name,
        "path": c.path,
        "url": c.html_url,
    } for c in res[:limit]]


def search_issues(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    res = _gh().search_issues(query=query)
    return [{
        "number": i.number,
        "title": i.title,
        "state": i.state,
        "url": i.html_url,
        "repo": i.repository.full_name,
    } for i in res[:limit]]


# ---------- gists ----------
def list_gists(user: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    u = _gh().get_user(user or config.GH_USER)
    return [{
        "id": g.id,
        "description": g.description,
        "public": g.public,
        "url": g.html_url,
        "files": list(g.files.keys()),
    } for g in u.get_gists()[:limit]]


def create_gist(description: str, content: str, filename: str = "snippet.txt",
                public: bool = False) -> Dict[str, Any]:
    u = _gh().get_user()
    g = u.create_gist(public=public, description=description, files={filename: content})
    return {"id": g.id, "url": g.html_url}


# ---------- meta ----------
def meta() -> Dict[str, Any]:
    return {
        "name": _NAME,
        "description": _DESCRIPTION,
        "version": _VERSION,
        "library": "PyGithub",
        "authenticated": bool(config.GH_TOKEN),
        "user": config.GH_USER,
    }
