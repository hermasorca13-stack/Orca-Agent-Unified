"""
skills/wikipedia_skill.py — Wikipedia via the official MediaWiki REST API v1.

Why this skill:
- The MediaWiki Action API (`/w/api.php`) is XML-heavy and clunky.
  The new REST API v1 (`/w/rest.php/v1/...`) returns clean JSON, no
  key, no rate limit beyond standard Wikimedia ToS.
- We use:
    GET https://en.wikipedia.org/w/rest.php/v1/search/page?q=...
    GET https://en.wikipedia.org/w/rest.php/v1/page/{title}
    GET https://en.wikipedia.org/w/rest.php/v1/page/{title}/bare

Public surface:
- `search(query, limit=5)` — title + snippet + url.
- `summary(title)` — short plaintext intro.
- `text(title, max_chars=10000)` — plaintext body (strips markup).
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

UA = "OrcaAgent/0.6 (+hermasorca13@gmail.com) — contact for ToS"
_BASE = "https://en.wikipedia.org/w/rest.php/v1"

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _http_get(path: str, params: Optional[Dict[str, Any]] = None, timeout: float = 10.0) -> Dict[str, Any]:
    # Always percent-encode the path segment (handles "—", "ü", etc.).
    base = _BASE.rstrip("/")
    enc_path = "/" + "/".join(
        urllib.parse.quote(seg, safe="") for seg in path.lstrip("/").split("/") if seg
    )
    url = f"{base}{enc_path}"
    if params:
        url += "?" + urllib.parse.urlencode(params, encoding="utf-8", safe="")
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
        try:
            return json.loads(raw.decode(charset))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return json.loads(raw.decode("utf-8", errors="replace"))


async def search(query: str, limit: int = 5) -> str:
    q = (query or "").strip()
    if not q:
        return "🔍 Empty query"
    limit = max(1, min(20, int(limit)))
    data = _http_get("/search/page", {"q": q, "limit": limit})
    pages = data.get("pages") or []
    if not pages:
        return f"🔍 No results for *{q}*"
    lines = [f"🔎 *Wikipedia: {q}*", ""]
    for p in pages:
        title = p.get("title") or "?"
        desc = p.get("description") or ""
        url = p.get("content_urls", {}).get("desktop", {}).get("page", "")
        snippet = (p.get("excerpt") or "").replace("<span class=\"searchmatch\">", "").replace("</span>", "")
        snippet = _TAG_RE.sub("", snippet).strip()
        line = f"• *{title}*"
        if desc:
            line += f"  — {desc}"
        lines.append(line)
        if snippet:
            lines.append(f"  _{snippet[:180]}_")
        if url:
            lines.append(f"  {url}")
    return "\n".join(lines)


def _strip_html(html: str) -> str:
    text = _TAG_RE.sub(" ", html)
    text = _WS_RE.sub(" ", text)
    return text.strip()


async def summary(title: str) -> str:
    t = (title or "").strip()
    if not t:
        return "🔍 Empty title"
    t_enc = urllib.parse.quote(t.replace(" ", "_"), safe="")
    data = _http_get(f"/page/{t_enc}/bare")
    extract = (data.get("extract") or "").strip()
    if not extract:
        return f"📭 No summary for *{t}*"
    short = _WS_RE.sub(" ", extract)
    if len(short) > 1200:
        short = short[:1200].rsplit(" ", 1)[0] + "…"
    return f"📚 *{data.get('title', t)}*\n\n{short}"


async def text(title: str, max_chars: int = 10000) -> str:
    """Return plaintext body of the page. Strips all HTML tags."""
    t = (title or "").strip()
    if not t:
        return "🔍 Empty title"
    t_enc = urllib.parse.quote(t.replace(" ", "_"), safe="")
    data = _http_get(f"/page/{t_enc}/bare")
    source = data.get("source") or ""
    body = _strip_html(source)
    if not body:
        body = (data.get("extract") or "").strip()
    if len(body) > max_chars:
        body = body[:max_chars].rsplit(" ", 1)[0] + "…"
    return body


# Backwards-compat: some callers passed raw strings. We always re-encode.
def _enc(title: str) -> str:
    # Full URL-encode (safe="") handles non-ASCII like "—" properly.
    return urllib.parse.quote(title.replace(" ", "_"), safe="")
