"""Emergency circuit breaker with durable state."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class KillSwitch:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def trigger(self, reason: str, *, close_positions: bool = True) -> dict[str, Any]:
        state = {"halted": True, "reason": reason, "close_positions": close_positions, "ts": datetime.now(timezone.utc).isoformat()}
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return state

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()

    def status(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"halted": False}
        return json.loads(self.path.read_text(encoding="utf-8"))
