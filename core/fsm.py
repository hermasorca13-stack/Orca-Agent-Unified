"""
core/fsm.py — Lightweight conversation state machine for multi-step flows.

Why: Telegram is stateless. When the bot asks a follow-up question
("which city?" / "what's the source currency?"), we need to remember the
user is in the middle of a flow and route their NEXT message accordingly.

This is add-only. Existing handlers are unaffected. New handlers can call
`fsm.push(user_id, FlowState(...))` before asking, and `fsm.consume(user_id)`
when a non-command message arrives.

States expire after FSM_TTL_SEC seconds (default 300) to prevent stale flows.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Optional

from loguru import logger


FSM_TTL_SEC = 300  # 5 min


class FlowKind(str, Enum):
    SETUP_API_KEY = "setup_api_key"          # /setup: waiting for LLM key
    SETUP_PROVIDER = "setup_provider"        # /setup: provider selected, waiting for key
    WEATHER_CITY = "weather_city"            # /weather without args
    TRANSLATE_PAIR = "translate_pair"        # /translate with no target
    FX_PAIR = "fx_pair"                      # /fx with no args
    PDF_URL = "pdf_url"                      # /pdf with no args
    CUSTOM = "custom"                        # generic


@dataclass
class FlowState:
    kind: FlowKind
    step: int = 0
    data: Dict[str, Any] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)
    on_message: Optional[Callable[["FlowState", str], Awaitable[str]]] = None

    @property
    def age_sec(self) -> float:
        return time.time() - self.started_at

    @property
    def expired(self) -> bool:
        return self.age_sec > FSM_TTL_SEC


class ConversationFSM:
    """In-memory FSM store keyed by user_id. Thread-safe enough for asyncio."""

    def __init__(self):
        self._states: Dict[int, FlowState] = {}

    def push(self, user_id: int, kind: FlowKind, **data) -> FlowState:
        st = FlowState(kind=kind, data=data)
        self._states[user_id] = st
        logger.debug(f"FSM push uid={user_id} kind={kind}")
        return st

    def get(self, user_id: int) -> Optional[FlowState]:
        st = self._states.get(user_id)
        if not st:
            return None
        if st.expired:
            self._states.pop(user_id, None)
            return None
        return st

    def consume(self, user_id: int) -> Optional[FlowState]:
        st = self.get(user_id)
        if st:
            self._states.pop(user_id, None)
        return st

    def cancel(self, user_id: int) -> bool:
        return self._states.pop(user_id, None) is not None

    def active(self) -> Dict[int, FlowState]:
        return {uid: st for uid, st in self._states.items() if not st.expired}

    def size(self) -> int:
        return len(self._states)


# Module-level singleton (imported by bot.py)
fsm = ConversationFSM()
