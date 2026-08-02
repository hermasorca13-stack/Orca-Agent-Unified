"""
skills/web_search_skill.py — Multi-provider web search.

Why this skill:
- Search is the foundation skill for research, fact-checking, news
  digests, and grounded LLM responses. The Orca agent already exposes
  /news (Google News RSS) and /wiki, but lacks a general-purpose
  web search. This skill fills that gap.
- We support 3 providers in priority order:
    1. Tavily  — purpose-built for AI agents; returns clean,
                 citation-ready content. Best results. Needs TAVILY_API_KEY.
    2. Serper  — Google SERP API; broader coverage, more raw. Needs SERPER_API_KEY.
    3. DuckDuckGo HTML — no key, limited (~20 results, no advanced filters),
                          best-effort scraping of the public HTML endpoint.
- Auto-pick: the first available key wins. Users can override with
  `provider=...`.

Public surface:
- `search(query, *, limit=5, provider="auto", timeout=15.0) -> dict`
  Returns a dict with: `query`, `provider`, `results` (list of
  {title, url, snippet}), `answer` (optional AI summary, Tavily only).
- `format_results(result, *, max_chars=3500) -> str` — Telegram-friendly
  Markdown card.
- `WebSearchError` — single, user-friendly exception class.

Engineering contract (Apple + Microsoft grade):
- Lazy-import provider SDKs (tavily, requests). Missing dep surfaces
  a clear error at call time, not at import time.
- Whitelist providers; reject unknowns with a clear hint.
- Cap results at 20 to keep the response snappy on Telegram.
- Friendly error messages for: missing query, all providers failed,
  rate limit, network error.
- loguru integration for telemetry.

This file is ADD-ONLY. It does not modify any existing module.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from loguru import logger


# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------
PROVIDERS = ("tavily", "serper", "duckduckgo")
DEFAULT_LIMIT = 5
MAX_LIMIT = 20
REQUEST_TIMEOUT = 15.0

_UA = "Orca-Agent/0.6 (+https://github.com/hermasorca13-stack/Orca-Agent-Unified)"


class WebSearchError(RuntimeError):
    """Raised when web search fails for any reason."""


# ----------------------------------------------------------------------
# Internal: provider detection
# ----------------------------------------------------------------------
def _active_provider(preferred: str) -> str:
    """Resolve the provider to use, in priority order."""
    if preferred and preferred != "auto":
        if preferred not in PROVIDERS:
            raise WebSearchError(
                f"Unknown provider {preferred!r}. Choose from: {list(PROVIDERS)}"
            )
        # The caller asked for a specific provider. Honour it even if
        # no key is set — the per-provider code will raise a clear
        # error if needed.
        return preferred
    if os.getenv("TAVILY_API_KEY", "").strip():
        return "tavily"
    if os.getenv("SERPER_API_KEY", "").strip():
        return "serper"
    return "duckduckgo"


# ----------------------------------------------------------------------
# Provider: Tavily
# ----------------------------------------------------------------------
def _search_tavily(query: str, limit: int, timeout: float) -> Dict[str, Any]:
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        raise WebSearchError(
            "TAVILY_API_KEY not set. Add it to .env, or use provider='duckduckgo'."
        )
    # Lazy import.
    try:
        from tavily import TavilyClient  # type: ignore
    except ImportError as exc:
        raise WebSearchError(
            "tavily-python SDK missing. Run: pip install tavily-python"
        ) from exc
    try:
        client = TavilyClient(api_key=api_key)
        resp = client.search(
            query=query,
            max_results=limit,
            search_depth="basic",
            include_answer=False,
        )
    except Exception as exc:  # noqa: BLE001
        raise WebSearchError(_friendly_tavily_error(str(exc))) from exc
    results: List[Dict[str, Any]] = []
    for r in resp.get("results", []) or []:
        results.append({
            "title": (r.get("title") or "").strip(),
            "url": (r.get("url") or "").strip(),
            "snippet": (r.get("content") or "").strip()[:600],
        })
    return {
        "query": query,
        "provider": "tavily",
        "results": results,
        "answer": None,
    }


def _friendly_tavily_error(raw: str) -> str:
    s = raw.lower()
    if "401" in s or "unauthorized" in s or "invalid api key" in s:
        return "TAVILY_API_KEY is invalid or revoked."
    if "429" in s or "rate" in s:
        return "Tavily rate-limited. Retry shortly."
    if "quota" in s or "billing" in s:
        return "Tavily quota exhausted."
    if "timeout" in s or "timed out" in s:
        return "Tavily timed out."
    return raw.splitlines()[0][:200] if raw else "Tavily error"


# ----------------------------------------------------------------------
# Provider: Serper (Google SERP)
# ----------------------------------------------------------------------
def _search_serper(query: str, limit: int, timeout: float) -> Dict[str, Any]:
    api_key = os.getenv("SERPER_API_KEY", "").strip()
    if not api_key:
        raise WebSearchError(
            "SERPER_API_KEY not set. Add it to .env, or use provider='duckduckgo'."
        )
    url = "https://google.serper.dev/search"
    payload = json.dumps({"q": query, "num": min(limit, MAX_LIMIT)}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
            "User-Agent": _UA,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            pass
        raise WebSearchError(
            _friendly_serper_error(exc.code, body)
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise WebSearchError(f"Serper request failed: {exc.__class__.__name__}") from exc

    results: List[Dict[str, Any]] = []
    for r in (data.get("organic") or [])[:limit]:
        results.append({
            "title": (r.get("title") or "").strip(),
            "url": (r.get("link") or "").strip(),
            "snippet": (r.get("snippet") or "").strip()[:600],
        })
    return {
        "query": query,
        "provider": "serper",
        "results": results,
        "answer": None,
    }


def _friendly_serper_error(code: int, body: str) -> str:
    if code == 401 or code == 403:
        return "SERPER_API_KEY is invalid or revoked."
    if code == 429:
        return "Serper rate-limited. Retry shortly."
    if 500 <= code < 600:
        return f"Serper server error {code}."
    return f"Serper HTTP {code}: {body[:120]}" if body else f"Serper HTTP {code}"


# ----------------------------------------------------------------------
# Provider: DuckDuckGo (no key)
# ----------------------------------------------------------------------
_DDG_RESULT_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?'
    r'class="result__snippet"[^>]*>(.*?)</a>',
    re.DOTALL | re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _search_duckduckgo(query: str, limit: int, timeout: float) -> Dict[str, Any]:
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({
        "q": query,
        "kl": "us-en",
    })
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        raise WebSearchError(
            f"DuckDuckGo request failed: {exc.__class__.__name__}: {str(exc)[:120]}"
        ) from exc

    results: List[Dict[str, Any]] = []
    for m in _DDG_RESULT_RE.finditer(html):
        raw_url, raw_title, raw_snippet = m.group(1), m.group(2), m.group(3)
        url_clean = urllib.parse.unquote(raw_url)
        title = _TAG_RE.sub("", raw_title).strip()
        snippet = _TAG_RE.sub("", raw_snippet).strip()[:600]
        if url_clean and title:
            results.append({
                "title": title,
                "url": url_clean,
                "snippet": snippet,
            })
        if len(results) >= limit:
            break

    if not results:
        # DDG sometimes returns a captcha / no-results page; surface a clear msg.
        raise WebSearchError(
            "DuckDuckGo returned no results. "
            "For reliable search, set TAVILY_API_KEY or SERPER_API_KEY."
        )

    return {
        "query": query,
        "provider": "duckduckgo",
        "results": results,
        "answer": None,
    }


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------
def search(
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    provider: str = "auto",
    timeout: float = REQUEST_TIMEOUT,
) -> Dict[str, Any]:
    """Run a web search and return normalised results.

    Args:
        query: search query string.
        limit: max results to return (1..20). Default 5.
        provider: 'auto', 'tavily', 'serper', or 'duckduckgo'.
        timeout: request timeout in seconds (default 15).

    Returns:
        dict with: query, provider, results (list of {title, url, snippet}),
        answer (optional AI summary — Tavily only, currently None).

    Raises:
        WebSearchError on any failure.
    """
    query = (query or "").strip()
    if not query:
        raise WebSearchError("Empty query")
    if limit < 1 or limit > MAX_LIMIT:
        raise WebSearchError(f"limit must be 1..{MAX_LIMIT} (got {limit})")

    prov = _active_provider(provider)
    t0 = time.monotonic()
    logger.info("web_search start | provider={} query={!r} limit={}", prov, query[:60], limit)

    if prov == "tavily":
        out = _search_tavily(query, limit, timeout)
    elif prov == "serper":
        out = _search_serper(query, limit, timeout)
    else:
        out = _search_duckduckgo(query, limit, timeout)

    elapsed = time.monotonic() - t0
    out["elapsed"] = round(elapsed, 2)
    logger.info(
        "web_search ok | provider={} results={} took={}s",
        prov, len(out["results"]), out["elapsed"],
    )
    return out


# ----------------------------------------------------------------------
# Format helpers (Telegram-friendly)
# ----------------------------------------------------------------------
def format_results(result: Dict[str, Any], *, max_chars: int = 3500) -> str:
    """Format a search result as a Telegram-friendly Markdown card."""
    provider = result.get("provider") or "?"
    query = result.get("query") or ""
    results = result.get("results") or []
    elapsed = float(result.get("elapsed") or 0)
    if not results:
        return f"🔍 No results for *{query}*  _(provider: {provider})_"
    lines = [
        f"🔍 *Search: {query}*",
        f"_Provider: {provider} • {len(results)} result(s) • {elapsed:.1f}s_",
        "",
    ]
    body = ""
    for i, r in enumerate(results, 1):
        title = r.get("title") or "(no title)"
        url = r.get("url") or ""
        snippet = r.get("snippet") or ""
        block = f"{i}. [{_md_escape(title)}]({url})"
        if snippet:
            block += f"\n   _{_md_escape(snippet)}_"
        if len(body) + len(block) + 2 > max_chars:
            lines.append(f"_…+{len(results) - i + 1} more result(s)_")
            break
        lines.append(block)
        body += block + "\n\n"
    return "\n".join(lines)


def _md_escape(text: str) -> str:
    """Escape Markdown-sensitive characters in plain text."""
    if not text:
        return ""
    # Telegram MarkdownV1: escape these.
    for ch in ("\\", "`", "*", "_", "["):
        text = text.replace(ch, f"\\{ch}")
    return text


__all__ = [
    "search", "format_results",
    "WebSearchError", "PROVIDERS", "DEFAULT_LIMIT", "MAX_LIMIT",
]
