"""Append-only JSONL audit trail with UTC timestamps and secret redaction."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_bot.models import jsonable

_SECRET = re.compile(r"(?i)(api[_-]?key|api[_-]?secret|password|token|private[_-]?key|passphrase)")


def redact(value: Any, key: str = "") -> Any:
    if _SECRET.search(key):
        return "[REDACTED]" if value else ""
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        return {str(k): redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item, key) for item in value]
    return jsonable(value)


class AuditLog:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: str, payload: Any = None) -> dict[str, Any]:
        record = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, "payload": redact(payload)}
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        return record
