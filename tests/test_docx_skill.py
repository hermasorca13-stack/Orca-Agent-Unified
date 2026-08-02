"""
Tests for skills/docx_skill.py.

Unit tests use a tmp directory and the skill's own public API. No
network. python-docx is required (it's in requirements.txt).
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL_PATH = ROOT / "skills" / "docx_skill.py"


def _load_skill():
    spec = importlib.util.spec_from_file_location(
        "docx_skill_under_test", str(SKILL_PATH)
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["docx_skill_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


mod = _load_skill()
info = mod.info
read = mod.read
tables = mod.tables
create = mod.create
append = mod.append
from_markdown = mod.from_markdown
format_info = mod.format_info
format_tables = mod.format_tables
DocxError = mod.DocxError


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
@pytest.fixture
def sample_docx(tmp_path):
    """Create a sample .docx with paragraphs and a table."""
    p = tmp_path / "sample.docx"
    create(
        str(p),
        title="Sample Document",
        paragraphs=["First paragraph.", "Second paragraph."],
        table=[["A", "B"], ["1", "2"], ["3", "4"]],
        author="Tester",
    )
    return p


# ----------------------------------------------------------------------
# Read
# ----------------------------------------------------------------------
class TestRead:
    def test_info_basic(self, sample_docx):
        meta = info(sample_docx)
        assert meta["title"] == "Sample Document"
        assert meta["author"] == "Tester"
        assert meta["paragraphs"] >= 3  # title heading + 2 paragraphs
        assert meta["tables"] == 1
        assert meta["size_bytes"] > 0

    def test_read_contains_text(self, sample_docx):
        text = read(sample_docx)
        assert "First paragraph." in text
        assert "Second paragraph." in text
        assert "A | B" in text  # table header

    def test_read_truncates(self, sample_docx):
        text = read(sample_docx, max_chars=20)
        assert "truncated" in text

    def test_tables(self, sample_docx):
        t = tables(sample_docx)
        assert len(t) == 1
        assert t[0][0] == ["A", "B"]
        assert t[0][1] == ["1", "2"]


# ----------------------------------------------------------------------
# Write
# ----------------------------------------------------------------------
class TestWrite:
    def test_create_minimal(self, tmp_path):
        p = create(str(tmp_path / "min.docx"))
        assert Path(p).exists()
        assert Path(p).suffix == ".docx"

    def test_create_with_table(self, tmp_path):
        p = create(
            str(tmp_path / "t.docx"),
            title="With Table",
            table=[["h1", "h2"], ["v1", "v2"]],
        )
        meta = info(p)
        assert meta["tables"] == 1
        assert meta["title"] == "With Table"

    def test_create_appends_docx_extension(self, tmp_path):
        p = create(str(tmp_path / "noext"))
        assert Path(p).suffix == ".docx"

    def test_append(self, sample_docx):
        append(sample_docx, "Appended line one.\nAppended line two.")
        text = read(sample_docx)
        assert "Appended line one." in text
        assert "Appended line two." in text

    def test_append_empty_raises(self, sample_docx):
        with pytest.raises(DocxError, match="Empty text"):
            append(sample_docx, "   ")

    def test_from_markdown_headings(self, tmp_path):
        p = from_markdown(
            "# Title\n\n## Sub\n\nbody",
            str(tmp_path / "md.docx"),
        )
        assert Path(p).exists()
        text = read(p)
        assert "Title" in text
        assert "Sub" in text
        assert "body" in text

    def test_from_markdown_lists(self, tmp_path):
        p = from_markdown(
            "- one\n- two\n- three\n\n1. first\n2. second",
            str(tmp_path / "md.docx"),
        )
        text = read(p)
        assert "one" in text and "two" in text and "three" in text
        assert "first" in text and "second" in text

    def test_from_markdown_code_block(self, tmp_path):
        p = from_markdown(
            "before\n\n```\nx = 1\n```\n\nafter",
            str(tmp_path / "md.docx"),
        )
        text = read(p)
        assert "x = 1" in text
        assert "before" in text
        assert "after" in text

    def test_from_markdown_empty_raises(self, tmp_path):
        with pytest.raises(DocxError, match="Empty Markdown"):
            from_markdown("", str(tmp_path / "x.docx"))


# ----------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------
class TestErrors:
    def test_missing_file(self):
        with pytest.raises(DocxError, match="File not found"):
            info("/no/such/file.docx")

    def test_bad_extension(self, tmp_path):
        bad = tmp_path / "x.txt"
        bad.write_text("hi")
        with pytest.raises(DocxError, match="Unsupported extension"):
            info(bad)

    def test_not_a_zip(self, tmp_path):
        fake = tmp_path / "fake.docx"
        fake.write_bytes(b"not a zip at all")
        with pytest.raises(DocxError, match="not a zip"):
            info(fake)

    def test_zip_missing_content_types(self, tmp_path):
        import zipfile
        p = tmp_path / "weird.docx"
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("hello.txt", "hi")
        with pytest.raises(DocxError, match="Content_Types"):
            info(p)

    def test_oversize_rejected(self, tmp_path):
        # We don't actually write a 100MB file in the test.
        # Mock the size check.
        with patch.object(mod, "MAX_BYTES", 4):
            good = tmp_path / "ok.docx"
            good.write_bytes(b"abcde")  # 5 bytes > mocked limit
            with pytest.raises(DocxError, match="too large"):
                info(good)


# ----------------------------------------------------------------------
# Format helpers
# ----------------------------------------------------------------------
class TestFormatters:
    def test_format_info(self):
        meta = {
            "title": "Hello",
            "author": "Me",
            "paragraphs": 5,
            "tables": 1,
            "sections": 1,
            "size_bytes": 1234,
        }
        out = format_info(meta)
        assert "Hello" in out
        assert "1,234 bytes" in out

    def test_format_tables_empty(self):
        out = format_tables([])
        assert "No tables" in out

    def test_format_tables_with_data(self):
        out = format_tables([[["a", "b"], ["1", "2"]]])
        assert "1 table" in out
        assert "a | b" in out


class TestSupportedExts:
    def test_only_docx(self):
        assert mod.SUPPORTED_EXTS == {".docx"}
