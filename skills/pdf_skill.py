"""
skills/pdf_skill.py — Read PDFs (text, metadata, tables) using pypdf and pdfplumber.

Why this skill:
- The system already has `pypdf` and `pdfplumber` installed.
- `pypdf` is fast and great for plain text + metadata (BSD license).
- `pdfplumber` (built on `pdfminer.six`) is the MIT winner for table
  extraction in 2026 (TEDS 0.847 on bordered tables per pdfmux.com
  benchmark). We use it only when tables are requested.

Public surface:
- `info(path)` — pages, title, author, size.
- `text(path, page=None, max_chars=20000)` — plain text.
- `summary(path, max_chars=4000)` — first N chars of the doc.
- `tables(path, page=None)` — list of tables (list of rows).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional


class PDFError(RuntimeError):
    pass


def _resolve(path: str) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    if not p.exists():
        raise PDFError(f"File not found: {p}")
    if p.suffix.lower() != ".pdf":
        raise PDFError(f"Not a PDF: {p}")
    return p


def info(path: str) -> Dict[str, Any]:
    p = _resolve(path)
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise PDFError(f"pypdf not available: {exc}")
    r = PdfReader(str(p))
    meta = r.metadata or {}
    return {
        "path": str(p),
        "size_bytes": p.stat().st_size,
        "pages": len(r.pages),
        "title": meta.get("/Title") or "",
        "author": meta.get("/Author") or "",
        "subject": meta.get("/Subject") or "",
    }


def text(path: str, page: Optional[int] = None, max_chars: int = 20000) -> str:
    p = _resolve(path)
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise PDFError(f"pypdf not available: {exc}")
    r = PdfReader(str(p))
    if page is not None:
        if page < 1 or page > len(r.pages):
            raise PDFError(f"Page {page} out of range 1..{len(r.pages)}")
        body = r.pages[page - 1].extract_text() or ""
    else:
        body = "\n\n".join((pg.extract_text() or "") for pg in r.pages)
    body = body.strip()
    if len(body) > max_chars:
        body = body[:max_chars] + "\n…[truncated]"
    return body


def summary(path: str, max_chars: int = 4000) -> str:
    p = _resolve(path)
    meta = info(path)
    head = (
        f"📄 *{meta['title'] or p.name}*\n"
        f"Author: {meta['author'] or '—'}  •  Pages: {meta['pages']}  •  "
        f"Size: {meta['size_bytes']} bytes\n\n"
    )
    body = text(path, max_chars=max_chars)
    return head + body


def tables(path: str, page: Optional[int] = None) -> List[List[List[str]]]:
    """Return tables as a list of (rows of cells). Empty list if none."""
    p = _resolve(path)
    try:
        import pdfplumber  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise PDFError(f"pdfplumber not available: {exc}")
    out: List[List[List[str]]] = []
    with pdfplumber.open(str(p)) as pdf:
        pages = [pdf.pages[page - 1]] if page else pdf.pages
        for i, pg in enumerate(pages, 1):
            ts = pg.extract_tables() or []
            for t in ts:
                # Clean cells: strip + handle None.
                clean = [[(c or "").strip() for c in row] for row in t]
                out.append(clean)
    return out
