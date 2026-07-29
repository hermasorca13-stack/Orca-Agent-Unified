"""
skills/arxiv_skill.py — Search arXiv for academic papers.

Why this skill:
- arXiv provides free, no-key, Atom XML access to 1M+ papers. The
  `arxiv` Python wrapper is the de-facto standard. We call it with
  a lazy import so the module loads even when `arxiv` is missing
  (caller gets a friendly error).

Public surface:
- `search(query, limit=5)` — returns formatted card with title,
  authors, year, abstract snippet, URL.
"""
from __future__ import annotations

import asyncio
import re
from typing import List, Optional


class ArxivError(RuntimeError):
    pass


_WS = re.compile(r"\s+")


async def search(query: str, limit: int = 5) -> str:
    q = (query or "").strip()
    if not q:
        return "🔍 Empty query"
    limit = max(1, min(20, int(limit)))

    try:
        import arxiv  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise ArxivError(
            "arxiv package not installed. Run: pip install arxiv"
        ) from exc

    def _do() -> List[dict]:
        client = arxiv.Client(page_size=limit, delay_seconds=2.0, num_retries=2)
        s = arxiv.Search(
            query=q,
            max_results=limit,
            sort_by=arxiv.SortCriterion.Relevance,
        )
        out: List[dict] = []
        for r in client.results(s):
            out.append(
                {
                    "title": (r.title or "").strip(),
                    "authors": [a.name for a in (r.authors or [])][:5],
                    "year": r.published.year if r.published else None,
                    "summary": _WS.sub(" ", (r.summary or "").strip())[:400],
                    "url": r.entry_id,
                    "pdf": r.pdf_url,
                }
            )
        return out

    try:
        items = await asyncio.to_thread(_do)
    except Exception as exc:  # noqa: BLE001
        raise ArxivError(f"arXiv search failed: {exc}") from exc

    if not items:
        return f"📭 No papers for *{q}*"

    lines = [f"📚 *arXiv: {q}*", ""]
    for i, it in enumerate(items, 1):
        title = it["title"].replace("\n", " ")
        lines.append(f"{i}. *{title}*")
        if it["authors"]:
            lines.append(f"   {', '.join(it['authors'])}{' et al.' if len(it['authors']) == 5 else ''} ({it['year']})")
        if it["summary"]:
            lines.append(f"   _{it['summary']}…_")
        if it["url"]:
            lines.append(f"   {it['url']}")
        lines.append("")
    return "\n".join(lines).rstrip()
