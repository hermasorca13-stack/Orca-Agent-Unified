"""tests/test_notes_skill.py - Unit tests for skills/notes_skill.py"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from skills.notes_skill import (
    Note,
    NoteStore,
    NotesSkill,
    _extract_tags,
    _strip_tags,
    fmt_note_line,
    format_list,
    format_search,
    get_skill,
)


@pytest.fixture
def tmp_store(tmp_path: Path) -> NoteStore:
    return NoteStore(tmp_path / "notes.json")


def _make_note(user_id=42, text="hello", tags=None) -> Note:
    now = datetime.now(timezone.utc).isoformat()
    return Note(
        id=f"n-{user_id}-{int(time.time()*1000)}",
        user_id=user_id,
        text=text,
        tags=tags or [],
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------
# Tag extraction
# ---------------------------------------------------------------------

class TestExtractTags:
    def test_no_tags(self):
        assert _extract_tags("plain text") == []

    def test_single_tag(self):
        assert _extract_tags("buy milk #shopping") == ["shopping"]

    def test_multiple_tags(self):
        tags = _extract_tags("a #one b #two c #three")
        assert tags == ["one", "two", "three"]

    def test_tag_dedup(self):
        tags = _extract_tags("#a #a #b #a")
        assert tags == ["a", "b"]

    def test_tag_case(self):
        tags = _extract_tags("#Shopping #SHOPPING")
        assert tags == ["shopping"]

    def test_tag_with_dash_underscore(self):
        tags = _extract_tags("a #work-life #todo_list b")
        assert tags == ["work-life", "todo_list"]

    def test_tag_too_long_ignored(self):
        # >32 chars get dropped
        tags = _extract_tags("#" + ("a" * 50) + " #ok")
        # regex [\w\-]{1,32} matches 1-32 chars, so 50-char tag has no match
        assert "ok" in tags
        assert all(len(t) <= 32 for t in tags)

    def test_strip_tags(self):
        assert _strip_tags("a #one b #two c") == "a b c"

    def test_strip_collapses_whitespace(self):
        assert _strip_tags("a  #x   b") == "a b"


# ---------------------------------------------------------------------
# NoteStore
# ---------------------------------------------------------------------

class TestNoteStore:
    def test_add_and_get(self, tmp_store):
        n = _make_note(text="hello")
        tmp_store.add(n)
        got = tmp_store.get(n.id)
        assert got is not None
        assert got.text == "hello"
        assert got.user_id == n.user_id

    def test_list_for_user_excludes_others(self, tmp_store):
        tmp_store.add(_make_note(user_id=42, text="a"))
        tmp_store.add(_make_note(user_id=42, text="b"))
        tmp_store.add(_make_note(user_id=99, text="c"))
        rows = tmp_store.list_for_user(42)
        assert len(rows) == 2
        assert all(r.user_id == 42 for r in rows)

    def test_list_for_user_filter_by_tag(self, tmp_store):
        tmp_store.add(_make_note(user_id=42, text="a", tags=["x"]))
        tmp_store.add(_make_note(user_id=42, text="b", tags=["y"]))
        tmp_store.add(_make_note(user_id=42, text="c", tags=["x", "z"]))
        rows = tmp_store.list_for_user(42, tag="x")
        assert len(rows) == 2
        assert {r.text for r in rows} == {"a", "c"}

    def test_list_sorted_newest_first(self, tmp_store):
        old = Note(
            id="n-1", user_id=42, text="old", tags=[],
            created_at="2020-01-01T00:00:00+00:00",
            updated_at="2020-01-01T00:00:00+00:00",
        )
        new = Note(
            id="n-2", user_id=42, text="new", tags=[],
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )
        tmp_store.add(old)
        tmp_store.add(new)
        rows = tmp_store.list_for_user(42)
        assert rows[0].id == "n-2"
        assert rows[1].id == "n-1"

    def test_search_substring(self, tmp_store):
        tmp_store.add(_make_note(user_id=42, text="buy milk"))
        tmp_store.add(_make_note(user_id=42, text="drink water"))
        rows = tmp_store.search(42, "milk")
        assert len(rows) == 1
        assert rows[0].text == "buy milk"

    def test_search_tag(self, tmp_store):
        tmp_store.add(_make_note(user_id=42, text="a", tags=["important"]))
        tmp_store.add(_make_note(user_id=42, text="b", tags=["junk"]))
        rows = tmp_store.search(42, "important")
        assert len(rows) == 1

    def test_search_case_insensitive(self, tmp_store):
        tmp_store.add(_make_note(user_id=42, text="Buy Milk"))
        rows = tmp_store.search(42, "milk")
        assert len(rows) == 1

    def test_search_excludes_other_users(self, tmp_store):
        tmp_store.add(_make_note(user_id=42, text="x"))
        tmp_store.add(_make_note(user_id=99, text="x"))
        rows = tmp_store.search(42, "x")
        assert len(rows) == 1

    def test_update_text(self, tmp_store):
        n = _make_note(user_id=42, text="a")
        tmp_store.add(n)
        updated = tmp_store.update_text(n.id, 42, "b")
        assert updated is not None
        assert updated.text == "b"
        assert updated.updated_at != n.created_at

    def test_update_other_user_blocked(self, tmp_store):
        n = _make_note(user_id=42, text="a")
        tmp_store.add(n)
        assert tmp_store.update_text(n.id, 99, "hacked") is None

    def test_add_tag(self, tmp_store):
        n = _make_note(user_id=42, text="a", tags=["x"])
        tmp_store.add(n)
        updated = tmp_store.add_tag(n.id, 42, "y")
        assert "y" in updated.tags
        assert "x" in updated.tags  # original preserved

    def test_add_tag_dedup(self, tmp_store):
        n = _make_note(user_id=42, text="a", tags=["x"])
        tmp_store.add(n)
        updated = tmp_store.add_tag(n.id, 42, "x")
        assert updated.tags.count("x") == 1

    def test_delete(self, tmp_store):
        n = _make_note(user_id=42)
        tmp_store.add(n)
        assert tmp_store.delete(n.id, 42) is True
        assert tmp_store.get(n.id) is None

    def test_delete_other_user_blocked(self, tmp_store):
        n = _make_note(user_id=42)
        tmp_store.add(n)
        assert tmp_store.delete(n.id, 99) is False
        assert tmp_store.get(n.id) is not None

    def test_persistence(self, tmp_path):
        p = tmp_path / "store.json"
        s1 = NoteStore(p)
        s1.add(_make_note(user_id=42, text="persist"))
        s2 = NoteStore(p)
        assert len(s2.list_for_user(42)) == 1

    def test_corrupt_json_recovers(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not json{", encoding="utf-8")
        s = NoteStore(p)
        assert s.count_for_user(42) == 0

    def test_thread_safety(self, tmp_store):
        def writer(i):
            tmp_store.add(_make_note(user_id=i % 5, text=f"t{i}"))
        threads = [threading.Thread(target=writer, args=(i,)) for i in range(30)]
        for t in threads: t.start()
        for t in threads: t.join()
        all_rows = tmp_store._read()
        assert len(all_rows) == 30


# ---------------------------------------------------------------------
# Note.matches
# ---------------------------------------------------------------------

class TestNoteMatches:
    def test_text_match(self):
        n = _make_note(text="buy milk")
        assert n.matches("milk") is True
        assert n.matches("buy") is True
        assert n.matches("xyz") is False

    def test_tag_match(self):
        n = _make_note(text="x", tags=["important"])
        assert n.matches("important") is True

    def test_case_insensitive(self):
        n = _make_note(text="Hello World")
        assert n.matches("hello") is True
        assert n.matches("WORLD") is True

    def test_empty_query(self):
        n = _make_note(text="x")
        assert n.matches("") is False
        assert n.matches("   ") is False


# ---------------------------------------------------------------------
# NotesSkill
# ---------------------------------------------------------------------

class TestNotesSkill:
    def test_add_extracts_tags(self, tmp_store):
        s = NotesSkill(store=tmp_store)
        n = s.add(42, "buy milk #shopping #groceries")
        assert n.tags == ["shopping", "groceries"]
        assert n.text == "buy milk"

    def test_add_no_tags(self, tmp_store):
        s = NotesSkill(store=tmp_store)
        n = s.add(42, "just text")
        assert n.tags == []
        assert n.text == "just text"

    def test_add_empty_raises(self, tmp_store):
        s = NotesSkill(store=tmp_store)
        with pytest.raises(ValueError):
            s.add(42, "")
        with pytest.raises(ValueError):
            s.add(42, "   #tagsonly   ")  # only tags, no text

    def test_list_user(self, tmp_store):
        s = NotesSkill(store=tmp_store)
        s.add(42, "a")
        s.add(42, "b")
        s.add(99, "c")
        assert len(s.list_user(42)) == 2

    def test_search(self, tmp_store):
        s = NotesSkill(store=tmp_store)
        s.add(42, "buy milk")
        s.add(42, "drink water")
        rows = s.search(42, "milk")
        assert len(rows) == 1

    def test_get_other_user_blocked(self, tmp_store):
        s = NotesSkill(store=tmp_store)
        n = s.add(42, "private")
        assert s.get(99, n.id) is None
        assert s.get(42, n.id) is not None

    def test_update(self, tmp_store):
        s = NotesSkill(store=tmp_store)
        n = s.add(42, "old")
        u = s.update(42, n.id, "new text")
        assert u is not None
        assert u.text == "new text"

    def test_update_other_user_blocked(self, tmp_store):
        s = NotesSkill(store=tmp_store)
        n = s.add(42, "x")
        assert s.update(99, n.id, "hacked") is None

    def test_tag(self, tmp_store):
        s = NotesSkill(store=tmp_store)
        n = s.add(42, "x")
        t = s.tag(42, n.id, "important")
        assert "important" in t.tags

    def test_tag_empty_raises(self, tmp_store):
        s = NotesSkill(store=tmp_store)
        n = s.add(42, "x")
        with pytest.raises(ValueError):
            s.tag(42, n.id, "")
        with pytest.raises(ValueError):
            s.tag(42, n.id, "   ")

    def test_delete(self, tmp_store):
        s = NotesSkill(store=tmp_store)
        n = s.add(42, "x")
        assert s.delete(42, n.id) is True
        assert s.delete(42, n.id) is False

    def test_delete_other_user_blocked(self, tmp_store):
        s = NotesSkill(store=tmp_store)
        n = s.add(42, "x")
        assert s.delete(99, n.id) is False


# ---------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------

class TestFormatters:
    def test_fmt_note_line_no_tags(self):
        n = _make_note(user_id=42, text="hello world", tags=[])
        line = fmt_note_line(n)
        assert "hello world" in line
        assert "[" not in line

    def test_fmt_note_line_with_tags(self):
        n = _make_note(user_id=42, text="a", tags=["x", "y"])
        line = fmt_note_line(n)
        assert "[x, y]" in line

    def test_fmt_note_line_long_text_truncated(self):
        n = _make_note(user_id=42, text="a" * 100, tags=[])
        line = fmt_note_line(n)
        assert "..." in line
        assert len(line) < 120  # reasonable

    def test_format_list_empty(self):
        out = format_list([])
        assert "No notes" in out
        assert "/note" in out

    def test_format_list_with_items(self):
        n1 = _make_note(user_id=42, text="a")
        n2 = _make_note(user_id=42, text="b")
        out = format_list([n1, n2])
        assert "Notes (2)" in out
        assert "a" in out
        assert "b" in out

    def test_format_search_no_results(self):
        out = format_search([], "nothing")
        assert "nothing" in out
        assert "No notes" in out

    def test_format_search_with_results(self):
        n = _make_note(user_id=42, text="buy milk")
        out = format_search([n], "milk")
        assert "Found 1" in out
        assert "milk" in out
        assert "buy milk" in out


# ---------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------

class TestEndToEnd:
    def test_full_lifecycle(self, tmp_store):
        s = NotesSkill(store=tmp_store)
        n = s.add(42, "buy milk #shopping")
        assert s.get(42, n.id).text == "buy milk"
        s.tag(42, n.id, "groceries")
        assert "groceries" in s.get(42, n.id).tags
        s.update(42, n.id, "buy milk and eggs #shopping #groceries")
        assert "eggs" in s.get(42, n.id).text
        assert len(s.search(42, "milk")) == 1
        assert len(s.search(42, "eggs")) == 1
        assert s.delete(42, n.id) is True
        assert s.get(42, n.id) is None

    def test_singleton_skill(self, tmp_path, monkeypatch):
        # Singleton is module-level; we test that get_skill() returns same instance
        s1 = get_skill()
        s2 = get_skill()
        assert s1 is s2

    def test_unicode_arabic_note(self, tmp_store):
        s = NotesSkill(store=tmp_store)
        n = s.add(42, "اشتري لبن #تسوق")
        assert "تسوق" in n.tags
        assert "اشتري لبن" in n.text
