"""
skills/notes_skill.py - Persistent notes for the Orca bot.

Net-new capability. Distinct from every other skill:
  - reminder = time-based trigger
  - shell    = ad-hoc command
  - this     = persistent text snippets with full-text search

Storage: data/notes.json (file-based, human-inspectable)
No external deps. Pure stdlib (json, re, datetime, uuid, threading).

NL examples that work:
  /note buy milk
  /note فكرة: استخدم خريطة ذهنية للتخطيط
  /note #shopping list of vegetables #groceries
  /note list
  /note search milk
  /note get <id>
  /note delete <id>
  /note tag <id> important

Each note:
  {
    "id":         "n-2026-08-03-001",
    "user_id":    123456,
    "text":       "buy milk",
    "tags":       ["shopping", "groceries"],
    "created_at": "2026-08-03T15:00:00+03:00",
    "updated_at": "2026-08-03T15:00:00+03:00",
  }
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger


_DEFAULT_PATH = Path("data/notes.json")


@dataclass
class Note:
    id: str
    user_id: int
    text: str
    tags: List[str]
    created_at: str
    updated_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Note":
        return cls(
            id=d["id"],
            user_id=d["user_id"],
            text=d.get("text", ""),
            tags=list(d.get("tags", [])),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", d.get("created_at", "")),
        )

    def matches(self, query: str) -> bool:
        """Case-insensitive substring match on text + tags."""
        q = query.lower().strip()
        if not q:
            return False
        if q in self.text.lower():
            return True
        for t in self.tags:
            if q in t.lower():
                return True
        return False


class NoteStore:
    """JSON file backed store. Thread-safe via RLock."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else _DEFAULT_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        if not self.path.exists():
            self._write([])

    def _read(self) -> List[Dict[str, Any]]:
        try:
            txt = self.path.read_text(encoding="utf-8")
            data = json.loads(txt) if txt.strip() else []
            if not isinstance(data, list):
                logger.warning("notes store: bad shape, resetting")
                data = []
            return data
        except FileNotFoundError:
            return []
        except json.JSONDecodeError as exc:
            logger.error("notes store: corrupt JSON ({}), resetting", exc)
            return []

    def _write(self, rows: List[Dict[str, Any]]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(self.path)

    def add(self, n: Note) -> Note:
        with self._lock:
            rows = self._read()
            rows.append(n.to_dict())
            self._write(rows)
            return n

    def get(self, nid: str) -> Optional[Note]:
        with self._lock:
            for row in self._read():
                if row.get("id") == nid:
                    return Note.from_dict(row)
            return None

    def list_for_user(self, user_id: int,
                      tag: Optional[str] = None) -> List[Note]:
        with self._lock:
            out: List[Note] = []
            for row in self._read():
                if row.get("user_id") != user_id:
                    continue
                if tag is not None:
                    tags = [t.lower() for t in row.get("tags", [])]
                    if tag.lower() not in tags:
                        continue
                out.append(Note.from_dict(row))
            out.sort(key=lambda n: n.created_at, reverse=True)
            return out

    def search(self, user_id: int, query: str) -> List[Note]:
        with self._lock:
            out: List[Note] = []
            for row in self._read():
                if row.get("user_id") != user_id:
                    continue
                n = Note.from_dict(row)
                if n.matches(query):
                    out.append(n)
            out.sort(key=lambda n: n.created_at, reverse=True)
            return out

    def update_text(self, nid: str, user_id: int, new_text: str) -> Optional[Note]:
        with self._lock:
            rows = self._read()
            now = datetime.now(timezone.utc).isoformat()
            for row in rows:
                if row.get("id") == nid and row.get("user_id") == user_id:
                    row["text"] = new_text
                    row["updated_at"] = now
                    self._write(rows)
                    return Note.from_dict(row)
            return None

    def add_tag(self, nid: str, user_id: int, tag: str) -> Optional[Note]:
        with self._lock:
            rows = self._read()
            now = datetime.now(timezone.utc).isoformat()
            for row in rows:
                if row.get("id") == nid and row.get("user_id") == user_id:
                    tags = list(row.get("tags", []))
                    if tag not in tags:
                        tags.append(tag)
                    row["tags"] = tags
                    row["updated_at"] = now
                    self._write(rows)
                    return Note.from_dict(row)
            return None

    def delete(self, nid: str, user_id: int) -> bool:
        with self._lock:
            rows = self._read()
            new = [r for r in rows
                   if not (r.get("id") == nid and r.get("user_id") == user_id)]
            if len(new) != len(rows):
                self._write(new)
                return True
            return False

    def count_for_user(self, user_id: int) -> int:
        with self._lock:
            return sum(1 for r in self._read() if r.get("user_id") == user_id)


class NotesSkill:
    """High-level API. Extracts tags from text and persists."""

    def __init__(self, store: Optional[NoteStore] = None) -> None:
        self.store = store or NoteStore()
        logger.info("NotesSkill ready (store={})", self.store.path)

    def add(self, user_id: int, text: str) -> Note:
        tags = _extract_tags(text)
        clean = _strip_tags(text).strip()
        if not clean:
            raise ValueError("note text is empty")
        now = datetime.now(timezone.utc).isoformat()
        nid = f"n-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        n = Note(
            id=nid,
            user_id=user_id,
            text=clean,
            tags=tags,
            created_at=now,
            updated_at=now,
        )
        self.store.add(n)
        logger.info("note added: {} for user {}", nid, user_id)
        return n

    def list_user(self, user_id: int, tag: Optional[str] = None) -> List[Note]:
        return self.store.list_for_user(user_id, tag)

    def search(self, user_id: int, query: str) -> List[Note]:
        return self.store.search(user_id, query)

    def get(self, user_id: int, nid: str) -> Optional[Note]:
        n = self.store.get(nid)
        if n and n.user_id == user_id:
            return n
        return None

    def delete(self, user_id: int, nid: str) -> bool:
        return self.store.delete(nid, user_id)

    def update(self, user_id: int, nid: str, new_text: str) -> Optional[Note]:
        return self.store.update_text(nid, user_id, new_text.strip())

    def tag(self, user_id: int, nid: str, tag: str) -> Optional[Note]:
        if not tag or not tag.strip():
            raise ValueError("tag is empty")
        return self.store.add_tag(nid, user_id, tag.strip())

    def stats(self) -> Dict[str, Any]:
        return {
            "path": str(self.store.path),
        }


# Tag extraction: words starting with # (max 32 chars, alphanumeric + dash + underscore)
_TAG_RE = re.compile(r"#([\w\-]{1,32})", re.UNICODE)


def _extract_tags(text: str) -> List[str]:
    seen = []
    seen_set = set()
    for m in _TAG_RE.finditer(text):
        tag = m.group(1).lower()
        if tag not in seen_set:
            seen.append(tag)
            seen_set.add(tag)
    return seen


def _strip_tags(text: str) -> str:
    """Remove #tag tokens from text, collapse whitespace."""
    cleaned = _TAG_RE.sub("", text)
    return re.sub(r"\s+", " ", cleaned).strip()


# Singleton
_skill: Optional[NotesSkill] = None


def get_skill() -> NotesSkill:
    global _skill
    if _skill is None:
        _skill = NotesSkill()
    return _skill


# Formatting helpers
def fmt_created(iso: str) -> str:
    try:
        d = datetime.fromisoformat(iso)
    except Exception:
        return iso
    return d.strftime("%Y-%m-%d %H:%M")


def fmt_note_line(n: Note) -> str:
    tags = f" [{', '.join(n.tags)}]" if n.tags else ""
    preview = n.text if len(n.text) <= 60 else n.text[:57] + "..."
    return f"  {n.id} - {fmt_created(n.created_at)}{tags} - {preview}"


def format_list(notes: List[Note]) -> str:
    if not notes:
        return "No notes yet. Use /note <text> to add one."
    lines = [f"Notes ({len(notes)}):"]
    lines.extend(fmt_note_line(n) for n in notes)
    return "\n".join(lines)


def format_search(notes: List[Note], query: str) -> str:
    if not notes:
        return f"No notes matching '{query}'."
    lines = [f"Found {len(notes)} note(s) matching '{query}':"]
    lines.extend(fmt_note_line(n) for n in notes)
    return "\n".join(lines)
