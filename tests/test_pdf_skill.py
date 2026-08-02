"""
Tests for skills/pdf_skill.py.

Unit tests cover both the existing read path and the new write/OCR
path. OCR is mocked because the Tesseract binary is not part of the
test environment on Windows.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import zlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL_PATH = ROOT / "skills" / "pdf_skill.py"


def _load_skill():
    spec = importlib.util.spec_from_file_location(
        "pdf_skill_under_test", str(SKILL_PATH)
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pdf_skill_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


mod = _load_skill()
info = mod.info
text = mod.text
summary = mod.summary
tables = mod.tables
to_pdf = mod.to_pdf
markdown_to_pdf = mod.markdown_to_pdf
ocr = mod.ocr
PDFError = mod.PDFError


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
@pytest.fixture
def empty_pdf(tmp_path):
    """Create a minimal valid PDF using reportlab (if available)."""
    p = tmp_path / "empty.pdf"
    to_pdf("Hello world.", str(p), title="Empty Test", author="Tester")
    return p


@pytest.fixture
def markdown_pdf(tmp_path):
    p = tmp_path / "from_md.pdf"
    md = (
        "# Title\n"
        "\n"
        "Intro paragraph.\n"
        "\n"
        "## Subheading\n"
        "\n"
        "- item 1\n"
        "- item 2\n"
        "\n"
        "1. first\n"
        "2. second\n"
        "\n"
        "```\n"
        "code line\n"
        "```\n"
    )
    markdown_to_pdf(md, str(p), title="MD Test")
    return p


# ----------------------------------------------------------------------
# Read path (regression — make sure existing behavior still works)
# ----------------------------------------------------------------------
class TestRead:
    def test_info(self, empty_pdf):
        meta = info(empty_pdf)
        assert meta["pages"] >= 1
        assert meta["title"] == "Empty Test"
        assert meta["author"] == "Tester"
        assert meta["size_bytes"] > 0

    def test_text(self, empty_pdf):
        body = text(empty_pdf)
        assert "Hello world" in body

    def test_text_truncates(self, empty_pdf):
        body = text(empty_pdf, max_chars=5)
        assert "truncated" in body

    def test_text_page_out_of_range(self, empty_pdf):
        with pytest.raises(PDFError, match="out of range"):
            text(empty_pdf, page=99)

    def test_summary(self, empty_pdf):
        s = summary(empty_pdf, max_chars=100)
        assert "Empty Test" in s
        assert "Hello world" in s

    def test_missing_file(self):
        with pytest.raises(PDFError, match="File not found"):
            info("/nope/missing.pdf")

    def test_not_a_pdf(self, tmp_path):
        bad = tmp_path / "x.txt"
        bad.write_text("hi")
        with pytest.raises(PDFError, match="Not a PDF"):
            info(bad)


# ----------------------------------------------------------------------
# Write: text → PDF
# ----------------------------------------------------------------------
class TestToPdf:
    def test_creates_valid_pdf(self, tmp_path):
        out = tmp_path / "out.pdf"
        p = to_pdf("Some text content here.", str(out))
        assert Path(p).exists()
        # Quick sanity: PDF magic header.
        with open(p, "rb") as f:
            head = f.read(8)
        assert head.startswith(b"%PDF-")

    def test_appends_pdf_extension(self, tmp_path):
        p = to_pdf("body", str(tmp_path / "noext"))
        assert Path(p).suffix == ".pdf"
        assert Path(p).exists()

    def test_with_title(self, tmp_path):
        p = to_pdf("body", str(tmp_path / "t.pdf"), title="My Title")
        # Read back the title via pypdf to confirm metadata.
        from pypdf import PdfReader
        r = PdfReader(p)
        assert r.metadata.get("/Title") == "My Title"

    def test_with_author(self, tmp_path):
        p = to_pdf("body", str(tmp_path / "a.pdf"), author="Alice")
        from pypdf import PdfReader
        r = PdfReader(p)
        assert r.metadata.get("/Author") == "Alice"

    def test_empty_text_raises(self, tmp_path):
        with pytest.raises(PDFError, match="Empty text"):
            to_pdf("   ", str(tmp_path / "x.pdf"))

    def test_long_text_paginates(self, tmp_path):
        # Generate enough text to span multiple pages.
        body = ("This is a paragraph.\n\n" * 200)
        p = to_pdf(body, str(tmp_path / "long.pdf"))
        meta = info(p)
        assert meta["pages"] >= 2

    def test_custom_page_size(self, tmp_path):
        p = to_pdf("body", str(tmp_path / "l.pdf"), page_size="Letter")
        assert Path(p).exists()

    def test_invalid_page_size_falls_back(self, tmp_path):
        # Unknown page size silently falls back to A4 (per the implementation).
        p = to_pdf("body", str(tmp_path / "fb.pdf"), page_size="Bogus")
        assert Path(p).exists()


# ----------------------------------------------------------------------
# Write: markdown → PDF
# ----------------------------------------------------------------------
class TestMarkdownToPdf:
    def test_creates_pdf(self, markdown_pdf):
        assert markdown_pdf.exists()
        with open(markdown_pdf, "rb") as f:
            assert f.read(8).startswith(b"%PDF-")

    def test_title_metadata(self, markdown_pdf):
        from pypdf import PdfReader
        r = PdfReader(markdown_pdf)
        assert r.metadata.get("/Title") == "MD Test"

    def test_empty_md_raises(self, tmp_path):
        with pytest.raises(PDFError, match="Empty Markdown"):
            markdown_to_pdf("   ", str(tmp_path / "x.pdf"))

    def test_headings(self, tmp_path):
        p = markdown_to_pdf(
            "# H1\n\n## H2\n\n### H3\n\nbody",
            str(tmp_path / "h.pdf"),
        )
        assert Path(p).exists()

    def test_lists(self, tmp_path):
        p = markdown_to_pdf(
            "- a\n- b\n- c\n\n1. one\n2. two",
            str(tmp_path / "l.pdf"),
        )
        assert Path(p).exists()

    def test_code_block(self, tmp_path):
        p = markdown_to_pdf(
            "before\n\n```\nx = 1\n```\n\nafter",
            str(tmp_path / "c.pdf"),
        )
        assert Path(p).exists()

    def test_inline_formatting(self, tmp_path):
        p = markdown_to_pdf(
            "**bold** and *italic* and `code`",
            str(tmp_path / "i.pdf"),
        )
        assert Path(p).exists()


# ----------------------------------------------------------------------
# OCR (mocked — Tesseract binary not available in test env)
# ----------------------------------------------------------------------
class TestOcr:
    def test_tesseract_missing_raises(self, tmp_path, monkeypatch):
        # Force the "not available" check.
        monkeypatch.setattr(mod, "_tesseract_available", lambda: False)
        p = tmp_path / "x.pdf"
        to_pdf("hi", str(p))
        with pytest.raises(PDFError, match="Tesseract binary not found"):
            ocr(p)

    def test_page_out_of_range(self, tmp_path, monkeypatch):
        # Mock tesseract available + the render call so we hit the page check.
        monkeypatch.setattr(mod, "_tesseract_available", lambda: True)
        p = tmp_path / "x.pdf"
        to_pdf("hi", str(p))
        # Patch pdf2image so we don't actually render.
        fake_pdf2image = MagicMock()
        with patch.dict(sys.modules, {"pdf2image": fake_pdf2image}):
            with pytest.raises(PDFError, match="out of range"):
                ocr(p, page=999)

    def test_language_pack_missing(self, tmp_path, monkeypatch):
        # Mock tesseract available, render returns a dummy image,
        # pytesseract raises language-not-found.
        monkeypatch.setattr(mod, "_tesseract_available", lambda: True)
        p = tmp_path / "x.pdf"
        to_pdf("hi", str(p))

        fake_pdf2image = MagicMock()
        fake_pdf2image.convert_from_path.return_value = [MagicMock()]
        fake_pytesseract = MagicMock()
        fake_pytesseract.image_to_string.side_effect = Exception(
            "could not create TXT output file: No such file or directory"
        )
        with patch.dict(sys.modules, {
            "pdf2image": fake_pdf2image,
            "pytesseract": fake_pytesseract,
        }):
            with pytest.raises(PDFError, match="language pack"):
                ocr(p, lang="zz")

    def test_success(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mod, "_tesseract_available", lambda: True)
        p = tmp_path / "x.pdf"
        to_pdf("hi", str(p))

        fake_pdf2image = MagicMock()
        fake_pdf2image.convert_from_path.return_value = [MagicMock(), MagicMock()]
        fake_pytesseract = MagicMock()
        fake_pytesseract.image_to_string.side_effect = ["page one text", "page two text"]
        with patch.dict(sys.modules, {
            "pdf2image": fake_pdf2image,
            "pytesseract": fake_pytesseract,
        }):
            out = ocr(p)
        assert "page one text" in out
        assert "page two text" in out


# ----------------------------------------------------------------------
# Module exports
# ----------------------------------------------------------------------
class TestExports:
    def test_all_in_all(self):
        for name in ("info", "text", "summary", "tables",
                     "to_pdf", "markdown_to_pdf", "ocr", "PDFError"):
            assert hasattr(mod, name), f"missing export: {name}"
