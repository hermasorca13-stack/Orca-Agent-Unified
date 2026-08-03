"""
skills/reminder_skill.py - Persistent reminder/scheduler for the Orca bot.

Net-new capability. Distinct from every other skill:
  - transcribe = audio -> text
  - termux    = phone control
  - intent    = NL routing
  - this      = "remind me to X at Y" + scheduled delivery

Storage: data/reminders.json (file-based, human-inspectable, no new deps)
Delivery: telegram_bot pulls due reminders and posts to user
Time parsing: pure stdlib (re, datetime, zoneinfo) - no dateparser
Threading: background thread polls every TICK_SEC; no external scheduler

NL examples that work:
  /remind in 30 minutes to call mom
  /remind after 1 hour check the oven
  /remind tomorrow at 9am meeting
  /remind 5m drink water
  /remind بعد ساعة أسمي ماما
  /remind بكرة الساعة 9 اجتماع
  /remind يوم الجمعة الساعة 8 صلاة

Patterns supported (English):
  - "in N (sec|min|minute|hour|hr|day)s?"
  - "after N (sec|min|hour|day)s?"
  - "tomorrow at HH:MM" / "tomorrow at H am|pm"
  - "today at HH:MM"
  - "at HH:MM"  (assumed today, future)
  - "every (mon|monday|...) HH:MM"  (recurring weekly)
  - "in 5m", "in 2h"  (shorthand)

Patterns supported (Arabic / Egyptian):
  - "بعد N (ثانية|دقيقة|ساعة|يوم)"
  - "بكرة الساعة H" / "بكرة H"
  - "النهارده الساعة H"
  - "الساعة H"  (future today)
  - "يوم (السبت|الأحد|...) الساعة H"
  - "كل (سبت|حد|...) H"  (recurring)

Schema:
  Reminder = {
    "id":         "r-2026-08-03-001",
    "user_id":    123456,
    "text":       "call mom",
    "due_at":     "2026-08-03T15:30:00+03:00",
    "created_at": "2026-08-03T15:00:00+03:00",
    "recurring":  "weekly",       # or null
    "status":     "pending",      # pending | sent | cancelled
    "sent_at":    null,
  }
"""
from __future__ import annotations

import json
import re
import threading
import time as _time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from loguru import logger

# ---------------------------------------------------------------------
# Storage layer (file-based JSON, no external deps)
# ---------------------------------------------------------------------

_DEFAULT_PATH = Path("data/reminders.json")
_TICK_SEC = 5.0   # how often the background thread polls


@dataclass
class Reminder:
    """One reminder. Plain dataclass (we serialize via asdict)."""
    id: str
    user_id: int
    text: str
    due_at: str           # ISO 8601 with timezone
    created_at: str
    recurring: Optional[str] = None   # "weekly" | None
    status: str = "pending"           # pending | sent | cancelled
    sent_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Reminder":
        return cls(**{k: d.get(k) for k in (
            "id","user_id","text","due_at","created_at",
            "recurring","status","sent_at"
        )})

    def is_due(self, now: Optional[datetime] = None) -> bool:
        if self.status != "pending":
            return False
        now = now or datetime.now(timezone.utc)
        try:
            due = datetime.fromisoformat(self.due_at)
        except Exception:
            return False
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        return due <= now


class ReminderStore:
    """JSON-file backed store. Thread-safe via internal lock."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else _DEFAULT_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        if not self.path.exists():
            self._write([])

    # ---- raw IO ----------------------------------------------------

    def _read(self) -> List[Dict[str, Any]]:
        try:
            txt = self.path.read_text(encoding="utf-8")
            data = json.loads(txt) if txt.strip() else []
            if not isinstance(data, list):
                logger.warning("reminder store: bad shape, resetting: {}", self.path)
                data = []
            return data
        except FileNotFoundError:
            return []
        except json.JSONDecodeError as exc:
            logger.error("reminder store: corrupt JSON ({}), resetting", exc)
            return []

    def _write(self, rows: List[Dict[str, Any]]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(self.path)

    # ---- CRUD ------------------------------------------------------

    def add(self, r: Reminder) -> Reminder:
        with self._lock:
            rows = self._read()
            rows.append(r.to_dict())
            self._write(rows)
            return r

    def get(self, rid: str) -> Optional[Reminder]:
        with self._lock:
            for row in self._read():
                if row.get("id") == rid:
                    return Reminder.from_dict(row)
            return None

    def list_for_user(self, user_id: int,
                      include_done: bool = False) -> List[Reminder]:
        with self._lock:
            out: List[Reminder] = []
            for row in self._read():
                if row.get("user_id") != user_id:
                    continue
                if not include_done and row.get("status") != "pending":
                    continue
                out.append(Reminder.from_dict(row))
            out.sort(key=lambda r: r.due_at)
            return out

    def list_due(self, now: Optional[datetime] = None) -> List[Reminder]:
        with self._lock:
            return [Reminder.from_dict(r) for r in self._read()
                    if Reminder.from_dict(r).is_due(now)]

    def mark_sent(self, rid: str) -> None:
        with self._lock:
            rows = self._read()
            for r in rows:
                if r.get("id") == rid:
                    r["status"] = "sent"
                    r["sent_at"] = datetime.now(timezone.utc).isoformat()
                    break
            self._write(rows)

    def cancel(self, rid: str, user_id: int) -> bool:
        with self._lock:
            rows = self._read()
            changed = False
            for r in rows:
                if r.get("id") == rid and r.get("user_id") == user_id \
                        and r.get("status") == "pending":
                    r["status"] = "cancelled"
                    changed = True
                    break
            if changed:
                self._write(rows)
            return changed

    def delete(self, rid: str, user_id: int) -> bool:
        with self._lock:
            rows = self._read()
            new = [r for r in rows
                   if not (r.get("id") == rid and r.get("user_id") == user_id)]
            if len(new) != len(rows):
                self._write(new)
                return True
            return False

    def count_pending(self) -> int:
        with self._lock:
            return sum(1 for r in self._read() if r.get("status") == "pending")


# ---------------------------------------------------------------------
# Time parser  (English + Arabic + Egyptian, stdlib only)
# ---------------------------------------------------------------------

# English relative: "in 30 minutes", "after 1 hour", "5m", "2h"
_EN_REL = re.compile(
    r"\b(?:in|after)\s+(\d+)\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|days?|d)\b",
    re.IGNORECASE,
)
_EN_SHORT = re.compile(r"\b(\d+)\s*(s|m|h|d)\b", re.IGNORECASE)
_EN_TOMORROW = re.compile(r"\btomorrow(?:\s+at)?\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
                          re.IGNORECASE)
_EN_TODAY = re.compile(r"\btoday(?:\s+at)?\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
                       re.IGNORECASE)
_EN_AT = re.compile(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.IGNORECASE)

# Arabic relative: "بعد 30 دقيقة", "بعد ساعة", "5 دقايق"
_AR_REL = re.compile(
    r"بعد\s+(\d+)\s*(ثانية|ثواني|دقيقة|دقايق|دقائق|ساعة|ساعات|يوم|ايام|أيام)",
    re.UNICODE,
)
_AR_SHORT = re.compile(r"(\d+)\s*(ث|د|س|ي)\b", re.UNICODE)
_AR_BOKRA = re.compile(r"بكرة(?:\s+الساعة)?\s*(\d{1,2})(?::(\d{2}))?", re.UNICODE)
_AR_NEHARDA = re.compile(r"(?:النهارده|النهاردة|النهاردة)(?:\s+الساعة)?\s*(\d{1,2})(?::(\d{2}))?",
                          re.UNICODE)
_AR_ASA = re.compile(r"الساعة\s+(\d{1,2})(?::(\d{2}))?", re.UNICODE)

# Weekday names (English + Arabic)
_EN_DAYS = {
    "mon": 0, "monday": 0,
    "tue": 1, "tues": 1, "tuesday": 1,
    "wed": 2, "wednesday": 2,
    "thu": 3, "thur": 3, "thurs": 3, "thursday": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}
_AR_DAYS = {
    "السبت": 5, "الاحد": 6, "الأحد": 6,
    "الاثنين": 0, "الإثنين": 0, "الثلاثاء": 1, "الاربعاء": 2, "الأربعاء": 2,
    "الخميس": 3, "الجمعة": 4,
}

# English unit -> seconds
_EN_UNITS = {
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
    "d": 86400, "day": 86400, "days": 86400,
}
# Arabic unit -> seconds
_AR_UNITS = {
    "ث": 1, "ثانية": 1, "ثواني": 1,
    "د": 60, "دقيقة": 60, "دقايق": 60, "دقائق": 60,
    "س": 3600, "ساعة": 3600, "ساعات": 3600,
    "ي": 86400, "يوم": 86400, "ايام": 86400, "أيام": 86400,
}


def _now_local() -> datetime:
    """Return current time in local timezone (with tzinfo)."""
    return datetime.now().astimezone()


def _next_weekday(target: int, hour: int, minute: int) -> datetime:
    """Next occurrence of weekday `target` (0=Mon..6=Sun) at hour:minute.
    If today is target and the time hasn't passed, return today.
    """
    now = _now_local()
    days_ahead = (target - now.weekday()) % 7
    candidate = (now + timedelta(days=days_ahead)).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )
    if days_ahead == 0 and candidate <= now:
        candidate += timedelta(days=7)
    return candidate


def _parse_clock(hour: int, minute: int = 0, ampm: Optional[str] = None) -> Tuple[int, int]:
    """Return 24h (hour, minute). ampm is 'am' or 'pm' (case-insensitive)."""
    if ampm:
        ampm = ampm.lower()
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"invalid clock {hour}:{minute}")
    return hour, minute


def parse_when(text: str, *, now: Optional[datetime] = None) -> Tuple[datetime, str, Optional[str]]:
    """Parse a natural-language time phrase and return (due_at, matched_text, recurring_kind).

    `recurring_kind` is "weekly" if a weekday pattern was detected, else None.
    Raises ValueError if no time pattern matched.
    """
    now = now or _now_local()
    text_lc = text.lower()

    # 1. English relative  ("in 5 minutes", "after 1 hour")
    m = _EN_REL.search(text)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        sec = _EN_UNITS.get(unit.rstrip("s") if unit not in _EN_UNITS else unit, 0) \
              or _EN_UNITS.get(unit, 0)
        if sec == 0:
            sec = _EN_UNITS.get(unit[:-1] if unit.endswith("s") else unit, 60)
        if sec == 0:
            raise ValueError(f"unknown unit: {unit}")
        due = now + timedelta(seconds=n * sec)
        return due, m.group(0), None

    # 2. English short  ("5m", "2h")
    m = _EN_SHORT.search(text)
    if m:
        n = int(m.group(1))
        u = m.group(2).lower()
        sec = _EN_UNITS.get(u, 0)
        if sec:
            return now + timedelta(seconds=n * sec), m.group(0), None

    # 3. Arabic relative  ("بعد 5 دقايق")
    m = _AR_REL.search(text)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        sec = _AR_UNITS.get(unit, 0)
        if sec == 0:
            raise ValueError(f"unknown arabic unit: {unit}")
        due = now + timedelta(seconds=n * sec)
        return due, m.group(0), None

    # 3b. Arabic relative with implicit 1  ("بعد ساعة", "بعد يوم")
    m = re.search(r"بعد\s+(ثانية|ثواني|دقيقة|دقايق|دقائق|ساعة|ساعات|يوم|ايام|أيام)", text, re.UNICODE)
    if m:
        unit = m.group(1)
        sec = _AR_UNITS.get(unit, 0)
        if sec:
            return now + timedelta(seconds=sec), m.group(0), None

    # 4. Arabic short  ("5د", "2س")
    m = _AR_SHORT.search(text)
    if m:
        n = int(m.group(1))
        u = m.group(2)
        sec = _AR_UNITS.get(u, 0)
        if sec:
            return now + timedelta(seconds=n * sec), m.group(0), None

    # 5a. English weekday  ("every monday at 9am")  -- BEFORE clock checks
    for name, idx in _EN_DAYS.items():
        if re.search(rf"\b(weekly|every)\s+{name}\b", text_lc):
            hour_match = _EN_AT.search(text) or _EN_TOMORROW.search(text)
            if hour_match:
                hour = int(hour_match.group(1))
                minute = int(hour_match.group(2) or 0)
                ampm = hour_match.group(3)
                hour, minute = _parse_clock(hour, minute, ampm)
                due = _next_weekday(idx, hour, minute)
                return due, f"weekly {name}", "weekly"

    # 5b. Arabic weekday  ("كل اثنين 9", "يوم الجمعة 8")  -- BEFORE clock checks
    for name, idx in _AR_DAYS.items():
        if name in text and ("كل" in text or "يوم" in text):
            # Try explicit clock first, then bare number at end
            m_at = _AR_ASA.search(text) or _AR_BOKRA.search(text) or _AR_NEHARDA.search(text)
            if m_at:
                hour = int(m_at.group(1))
                minute = int(m_at.group(2) or 0)
                hour, minute = _parse_clock(hour, minute, None)
                due = _next_weekday(idx, hour, minute)
                return due, f"weekly {name}", "weekly"
            # Bare number at end: "كل جمعة 8" -> 8:00
            m_bare = re.search(r"(\d{1,2})(?::(\d{2}))?\s*$", text)
            if m_bare:
                hour = int(m_bare.group(1))
                minute = int(m_bare.group(2) or 0)
                hour, minute = _parse_clock(hour, minute, None)
                due = _next_weekday(idx, hour, minute)
                return due, f"weekly {name}", "weekly"

    # 6. English tomorrow  ("tomorrow at 9am")
    m = _EN_TOMORROW.search(text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        ampm = m.group(3)
        hour, minute = _parse_clock(hour, minute, ampm)
        due = (now + timedelta(days=1)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        return due, m.group(0), None

    # 6. English today  ("today at 5pm")
    m = _EN_TODAY.search(text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        ampm = m.group(3)
        hour, minute = _parse_clock(hour, minute, ampm)
        due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if due <= now:
            due += timedelta(days=1)
        return due, m.group(0), None

    # 7. English at-time  ("at 5pm")
    m = _EN_AT.search(text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        ampm = m.group(3)
        hour, minute = _parse_clock(hour, minute, ampm)
        due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if due <= now:
            due += timedelta(days=1)
        return due, m.group(0), None

    # 8. Arabic bokra  ("بكرة 9", "بكرة الساعة 9:30")
    m = _AR_BOKRA.search(text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        if not (0 <= hour <= 23):
            hour %= 12  # 12-hour fallback for Egyptian AM/PM
        due = (now + timedelta(days=1)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        return due, m.group(0), None

    # 9. Arabic neharda  ("النهارده 5")
    m = _AR_NEHARDA.search(text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        hour, minute = _parse_clock(hour, minute, None)
        due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if due <= now:
            due += timedelta(days=1)
        return due, m.group(0), None

    # 10. Arabic asa  ("الساعة 9")
    m = _AR_ASA.search(text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        hour, minute = _parse_clock(hour, minute, None)
        due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if due <= now:
            due += timedelta(days=1)
        return due, m.group(0), None

    # (weekday checks moved up, before clock checks)

    raise ValueError(f"could not parse time from: {text!r}")


# ---------------------------------------------------------------------
# ReminderSkill - the public surface the bot uses
# ---------------------------------------------------------------------

class ReminderSkill:
    """High-level API: parse user text -> store -> background tick."""

    def __init__(self, store: Optional[ReminderStore] = None) -> None:
        self.store = store or ReminderStore()
        self._on_due: Optional[Callable[[Reminder], None]] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        logger.info("ReminderSkill ready (store={})", self.store.path)

    # ---- bot hooks ------------------------------------------------

    def set_delivery_callback(self, fn: Callable[[Reminder], None]) -> None:
        """Bot registers a callback that gets the due reminder and
        posts it to Telegram. We never import telegram_bot here
        (no circular dep, lazy coupling)."""
        self._on_due = fn

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="ReminderSkill-tick", daemon=True
        )
        self._thread.start()
        logger.info("ReminderSkill background thread started")

    def stop(self) -> None:
        self._stop.set()

    # ---- public API -----------------------------------------------

    def remind(self, user_id: int, text: str) -> Reminder:
        """Parse `text` for a time phrase; everything else is the
        reminder body. Returns the persisted Reminder.

        Raises ValueError if no time phrase is found.
        """
        due_at, matched, recurring = parse_when(text)
        body = _strip_time_phrase(text, matched).strip()
        if not body:
            body = "(no description)"
        now = datetime.now().astimezone()
        rid = f"r-{now.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        r = Reminder(
            id=rid,
            user_id=user_id,
            text=body,
            due_at=due_at.isoformat(),
            created_at=now.isoformat(),
            recurring=recurring,
        )
        self.store.add(r)
        logger.info("reminder created: {} for user {} due {}", rid, user_id, due_at)
        return r

    def list_user(self, user_id: int) -> List[Reminder]:
        return self.store.list_for_user(user_id, include_done=False)

    def cancel(self, user_id: int, rid: str) -> bool:
        return self.store.cancel(rid, user_id)

    def delete(self, user_id: int, rid: str) -> bool:
        return self.store.delete(rid, user_id)

    def stats(self) -> Dict[str, Any]:
        return {
            "path": str(self.store.path),
            "pending": self.store.count_pending(),
            "thread_alive": bool(self._thread and self._thread.is_alive()),
            "tick_sec": _TICK_SEC,
        }

    # ---- background loop ------------------------------------------

    def _loop(self) -> None:
        logger.info("ReminderSkill tick loop running (every {:.1f}s)", _TICK_SEC)
        while not self._stop.is_set():
            try:
                self._tick_once()
            except Exception as exc:
                logger.error("ReminderSkill tick error: {}", exc)
            self._stop.wait(_TICK_SEC)

    def _tick_once(self) -> None:
        due = self.store.list_due()
        if not due:
            return
        for r in due:
            try:
                if self._on_due is not None:
                    self._on_due(r)
                # mark sent (or reschedule if recurring)
                if r.recurring == "weekly":
                    self._reschedule_weekly(r)
                else:
                    self.store.mark_sent(r.id)
            except Exception as exc:
                logger.error("ReminderSkill delivery failed for {}: {}", r.id, exc)

    def _reschedule_weekly(self, r: Reminder) -> None:
        try:
            old = datetime.fromisoformat(r.due_at)
        except Exception:
            return
        if old.tzinfo is None:
            old = old.replace(tzinfo=timezone.utc)
        new_due = (old + timedelta(days=7)).isoformat()
        # rewrite row
        with self.store._lock:  # type: ignore[attr-defined]
            rows = self.store._read()  # type: ignore[attr-defined]
            for row in rows:
                if row.get("id") == r.id:
                    row["due_at"] = new_due
                    row["status"] = "pending"
                    row["sent_at"] = datetime.now(timezone.utc).isoformat()
                    break
            self.store._write(rows)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------

def _strip_time_phrase(text: str, phrase: str) -> str:
    """Remove the matched time phrase from the original text to leave
    just the reminder body. Case-insensitive, phrase boundary aware."""
    if not phrase:
        return text
    pattern = re.escape(phrase)
    return re.sub(pattern, "", text, count=1, flags=re.IGNORECASE | re.UNICODE).strip()


# ---------------------------------------------------------------------
# Module-level singleton (lazy)
# ---------------------------------------------------------------------

_skill: Optional[ReminderSkill] = None


def get_skill() -> ReminderSkill:
    global _skill
    if _skill is None:
        _skill = ReminderSkill()
    return _skill


# ---------------------------------------------------------------------
# Telegram-side formatting helpers
# ---------------------------------------------------------------------

def fmt_due(due_iso: str) -> str:
    """Render ISO due time as a friendly relative string for Telegram."""
    try:
        due = datetime.fromisoformat(due_iso)
    except Exception:
        return due_iso
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    delta = due - now
    secs = int(delta.total_seconds())
    if abs(secs) < 60:
        return "now"
    if secs > 0 and secs < 3600:
        return f"in {secs // 60}m"
    if secs < 0 and abs(secs) < 3600:
        return f"{-secs // 60}m ago"
    if secs > 0 and secs < 86400:
        return f"in {secs // 3600}h {(secs % 3600) // 60}m"
    if secs < 0 and abs(secs) < 86400:
        return f"{-secs // 3600}h ago"
    return due.strftime("%Y-%m-%d %H:%M")


def fmt_reminder_line(r: Reminder) -> str:
    due = fmt_due(r.due_at)
    recur = " (weekly)" if r.recurring == "weekly" else ""
    return f"  {r.id} - {due}{recur} - {r.text}"


def format_list(reminders: List[Reminder]) -> str:
    if not reminders:
        return "No pending reminders. Use /remind to set one."
    lines = ["Pending reminders:"]
    lines.extend(fmt_reminder_line(r) for r in reminders)
    return "\n".join(lines)
