"""
skills/pdf_skill.py — Read & write PDFs using pypdf, pdfplumber, and reportlab.

Why this skill:
- The system already has `pypdf` and `pdfplumber` installed.
- `pypdf` is fast and great for plain text + metadata (BSD license).
- `pdfplumber` (built on `pdfminer.six`) is the MIT winner for table
  extraction in 2026 (TEDS 0.847 on bordered tables per pdfmux.com
  benchmark). We use it only when tables are requested.
- `reportlab` is the consensus standard for *generating* PDFs in pure
  Python (BSD, no native deps). It joins the existing reader stack to
  give the skill write capability: text → PDF, markdown → PDF.
- `pytesseract` + `pdf2image` add OCR for scanned / image-based PDFs
  (Tesseract binary is an optional system dep — gracefully detected).

Public surface:
- `info(path)` — pages, title, author, size.
- `text(path, page=None, max_chars=20000)` — plain text.
- `summary(path, max_chars=4000)` — first N chars of the doc.
- `tables(path, page=None)` — list of tables (list of rows).
- `to_pdf(text, out_path, *, title=None, author=None, page_size="A4",
  font_size=11)` — generate a PDF from plain text.
- `markdown_to_pdf(md, out_path, *, title=None, author=None)` —
  generate a PDF from Markdown (headings, bold/italic, bullets,
  numbered lists, code blocks, paragraphs).
- `ocr(path, *, page=None, lang="eng", dpi=200)` — OCR a PDF page
  (or whole doc). Requires the `tesseract` binary on PATH.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class PDFError(RuntimeError):
    pass


# ----------------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------------
def _resolve(path: Union[str, Path]) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    if not p.exists():
        raise PDFError(f"File not found: {p}")
    if p.suffix.lower() != ".pdf":
        raise PDFError(f"Not a PDF: {p}")
    return p


def _out_path(out_path: Union[str, Path]) -> Path:
    out = Path(out_path).expanduser()
    if not out.is_absolute():
        out = (Path.cwd() / out).resolve()
    if out.suffix.lower() != ".pdf":
        out = out.with_suffix(".pdf")
    out.parent.mkdir(parents=True, exist_ok=True)
    return out


# ----------------------------------------------------------------------
# Read
# ----------------------------------------------------------------------
def info(path: Union[str, Path]) -> Dict[str, Any]:
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


def text(path: Union[str, Path], page: Optional[int] = None, max_chars: int = 20000) -> str:
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


def summary(path: Union[str, Path], max_chars: int = 4000) -> str:
    p = _resolve(path)
    meta = info(path)
    head = (
        f"📄 *{meta['title'] or p.name}*\n"
        f"Author: {meta['author'] or '—'}  •  Pages: {meta['pages']}  •  "
        f"Size: {meta['size_bytes']} bytes\n\n"
    )
    body = text(path, max_chars=max_chars)
    return head + body


def tables(path: Union[str, Path], page: Optional[int] = None) -> List[List[List[str]]]:
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


# ----------------------------------------------------------------------
# Write
# ----------------------------------------------------------------------
def to_pdf(
    text: str,
    out_path: Union[str, Path],
    *,
    title: Optional[str] = None,
    author: Optional[str] = None,
    page_size: str = "A4",
    font_size: int = 11,
) -> str:
    """Generate a PDF from plain text.

    Args:
        text: body text. Newlines become paragraph breaks. Long lines
            wrap automatically.
        out_path: where to write the file. `.pdf` is appended if missing.
        title: optional PDF title (also rendered as the first heading).
        author: optional author metadata.
        page_size: 'A4' (default), 'Letter', or 'Legal'.
        font_size: in points (default 11).

    Returns:
        Absolute path of the generated PDF as a string.

    Raises:
        PDFError on any failure.
    """
    text = text or ""
    if not text.strip():
        raise PDFError("Empty text — nothing to write")

    try:
        from reportlab.lib.pagesizes import A4, LETTER, LEGAL  # type: ignore
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle  # type: ignore
        from reportlab.lib.units import cm  # type: ignore
        from reportlab.platypus import (  # type: ignore
            SimpleDocTemplate, Paragraph, Spacer, PageBreak,
        )
    except ImportError as exc:
        raise PDFError(
            "reportlab not installed. Run: pip install 'reportlab>=4.0.0'"
        ) from exc

    out = _out_path(out_path)
    sizes = {"A4": A4, "Letter": LETTER, "Legal": LEGAL}
    ps = sizes.get(page_size, A4)

    doc = SimpleDocTemplate(
        str(out),
        pagesize=ps,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title=title or "Orca Document",
        author=author or "Orca Agent",
    )

    styles = getSampleStyleSheet()
    body_style = ParagraphStyle(
        "body", parent=styles["BodyText"],
        fontSize=font_size, leading=font_size * 1.4, spaceAfter=8,
    )
    heading_style = ParagraphStyle(
        "h1", parent=styles["Heading1"],
        fontSize=font_size + 8, spaceAfter=12, spaceBefore=6,
    )

    flow: List[Any] = []
    if title:
        flow.append(Paragraph(_xml_escape(title), heading_style))
        flow.append(Spacer(1, 0.3 * cm))
    # Split on blank lines → paragraphs.
    for para in re.split(r"\n\s*\n", text.strip()):
        para = para.strip()
        if not para:
            continue
        # reportlab Paragraph handles line breaks via <br/>.
        para = _xml_escape(para).replace("\n", "<br/>")
        flow.append(Paragraph(para, body_style))
        flow.append(Spacer(1, 0.15 * cm))

    try:
        doc.build(flow)
    except Exception as exc:  # noqa: BLE001
        raise PDFError(f"reportlab build failed: {exc}") from exc
    return str(out.resolve())


def markdown_to_pdf(
    md: str,
    out_path: Union[str, Path],
    *,
    title: Optional[str] = None,
    author: Optional[str] = None,
) -> str:
    """Best-effort Markdown → PDF.

    Supports:
    - `# H1` … `###### H6` → Word-style headings (level 1–6)
    - `- item` / `* item` → bullet list
    - `1. item` → numbered list
    - Triple-backtick code blocks → monospace paragraphs
    - `**bold**` / `*italic*` / `` `code` `` → inline
    - Paragraphs of plain text

    Returns the absolute output path.
    """
    md = (md or "").strip()
    if not md:
        raise PDFError("Empty Markdown input")

    try:
        from reportlab.lib.pagesizes import A4  # type: ignore
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle  # type: ignore
        from reportlab.lib.units import cm  # type: ignore
        from reportlab.platypus import (  # type: ignore
            SimpleDocTemplate, Paragraph, Spacer,
        )
    except ImportError as exc:
        raise PDFError(
            "reportlab not installed. Run: pip install 'reportlab>=4.0.0'"
        ) from exc

    out = _out_path(out_path)
    doc = SimpleDocTemplate(
        str(out), pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title=title or "Orca Markdown",
        author=author or "Orca Agent",
    )
    styles = getSampleStyleSheet()
    h_styles = {
        n: ParagraphStyle(
            f"h{n}", parent=styles[f"Heading{n}"],
            spaceBefore=8, spaceAfter=6,
        )
        for n in range(1, 7)
    }
    body = ParagraphStyle(
        "body", parent=styles["BodyText"], fontSize=11, leading=15, spaceAfter=6,
    )
    code = ParagraphStyle(
        "code", parent=styles["Code"], fontSize=9, leading=11, leftIndent=12, spaceAfter=6,
    )
    list_bullet = ParagraphStyle(
        "lb", parent=body, leftIndent=18, bulletIndent=6, spaceAfter=2,
    )
    list_num = ParagraphStyle(
        "ln", parent=body, leftIndent=18, bulletIndent=6, spaceAfter=2,
    )

    flow: List[Any] = []
    in_code = False
    code_buf: List[str] = []
    list_buf: List[str] = []
    list_kind: Optional[str] = None

    def flush_list() -> None:
        nonlocal list_buf, list_kind
        if not list_buf:
            return
        style = list_bullet if list_kind == "bullet" else list_num
        for item in list_buf:
            flow.append(Paragraph(_inline_md_to_xml(item), style))
        list_buf = []
        list_kind = None

    for raw in md.splitlines():
        line = raw.rstrip()

        if line.strip().startswith("```"):
            if in_code:
                if code_buf:
                    flow.append(Paragraph(
                        _xml_escape("\n".join(code_buf)).replace("\n", "<br/>"),
                        code,
                    ))
                code_buf = []
                in_code = False
            else:
                flush_list()
                in_code = True
            continue
        if in_code:
            code_buf.append(line)
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            flush_list()
            level = min(6, max(1, len(m.group(1))))
            flow.append(Paragraph(
                _inline_md_to_xml(m.group(2).strip()),
                h_styles[level],
            ))
            continue

        m = re.match(r"^[\-\*]\s+(.*)$", line)
        if m:
            if list_kind != "bullet":
                flush_list()
                list_kind = "bullet"
            list_buf.append(m.group(1).strip())
            continue

        m = re.match(r"^\d+\.\s+(.*)$", line)
        if m:
            if list_kind != "numbered":
                flush_list()
                list_kind = "numbered"
            list_buf.append(m.group(1).strip())
            continue

        if not line.strip():
            flush_list()
            continue

        flush_list()
        flow.append(Paragraph(_inline_md_to_xml(line.strip()), body))

    flush_list()
    if in_code and code_buf:
        flow.append(Paragraph(
            _xml_escape("\n".join(code_buf)).replace("\n", "<br/>"),
            code,
        ))

    try:
        doc.build(flow)
    except Exception as exc:  # noqa: BLE001
        raise PDFError(f"reportlab build failed: {exc}") from exc
    return str(out.resolve())


# ----------------------------------------------------------------------
# OCR (scanned / image-based PDFs)
# ----------------------------------------------------------------------
def _tesseract_available() -> bool:
    """Check if the `tesseract` binary is on PATH."""
    return shutil.which("tesseract") is not None


def ocr(
    path: Union[str, Path],
    *,
    page: Optional[int] = None,
    lang: str = "eng",
    dpi: int = 200,
) -> str:
    """OCR a PDF page (or whole doc) via Tesseract.

    Args:
        path: input PDF.
        page: 1-based page index, or None for all pages.
        lang: Tesseract language code ('eng', 'ara', 'ara+eng', …).
        dpi: render DPI (higher = better accuracy, slower).

    Returns:
        The OCR'd text. Pages are joined with blank lines.

    Raises:
        PDFError if tesseract, pdf2image, or pytesseract is missing.
    """
    p = _resolve(path)
    if not _tesseract_available():
        raise PDFError(
            "Tesseract binary not found on PATH. "
            "Install it (Windows: choco install tesseract, "
            "macOS: brew install tesseract, Linux: apt install tesseract-ocr) "
            "and ensure the `tesseract` command is on PATH."
        )
    try:
        from pdf2image import convert_from_path  # type: ignore
    except ImportError as exc:
        raise PDFError(
            "pdf2image not installed. Run: pip install pdf2image "
            "(also requires poppler on your system)"
        ) from exc
    try:
        import pytesseract  # type: ignore
    except ImportError as exc:
        raise PDFError(
            "pytesseract not installed. Run: pip install pytesseract"
        ) from exc

    # Render pages.
    if page is not None:
        from pypdf import PdfReader  # type: ignore
        r = PdfReader(str(p))
        if page < 1 or page > len(r.pages):
            raise PDFError(f"Page {page} out of range 1..{len(r.pages)}")
        images = convert_from_path(str(p), dpi=dpi, first_page=page, last_page=page)
    else:
        images = convert_from_path(str(p), dpi=dpi)

    parts: List[str] = []
    for i, img in enumerate(images, 1):
        try:
            t = pytesseract.image_to_string(img, lang=lang)
        except Exception as exc:  # noqa: BLE001
            # Tesseract raises a few different messages for missing
            # language data. Catch the common patterns.
            msg = str(exc).lower()
            if (
                "could not create txt" in msg
                or "failed loading language" in msg
                or "traineddata" in msg
                or "tesseract couldn't load" in msg
            ):
                raise PDFError(
                    f"Tesseract language pack {lang!r} not installed. "
                    f"Install with: apt install tesseract-ocr-{lang} "
                    f"(or brew install tesseract-lang)."
                ) from exc
            raise PDFError(f"Tesseract failed on page {i}: {exc}") from exc
        parts.append(t.strip())
    return "\n\n".join(parts).strip()


# ----------------------------------------------------------------------
# Internal text-formatting helpers
# ----------------------------------------------------------------------
def _xml_escape(s: str) -> str:
    """Escape XML/HTML for reportlab Paragraph."""
    if not s:
        return ""
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
    )


def _inline_md_to_xml(s: str) -> str:
    """Convert inline Markdown (**bold**, *italic*, `code`) to reportlab tags."""
    s = _xml_escape(s)
    # Code spans first (so we don't bold inside them).
    s = re.sub(r"`([^`]+)`", r'<font face="Courier">\1</font>', s)
    # Bold (**...**).
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    # Italic (*...*).
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", s)
    return s


__all__ = [
    "info", "text", "summary", "tables",
    "to_pdf", "markdown_to_pdf", "ocr",
    "PDFError",
]

