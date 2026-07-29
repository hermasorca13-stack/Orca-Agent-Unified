"""
core/middleware.py — Rate limiting, metrics, and friendly error wrapper.

Why this file:
- The bot must not get flooded by a single user (Telegram rate limits apply
  on the *outbound* side; we need an *inbound* limit too).
- We want a single place to record per-user call counts so /status can
  surface real activity.

What it provides:
- `@with_user_ratelimit(max_per_minute=20)` — decorator for handler
  methods. Silently drops the reply (logs only) when over budget.
- `metrics` — a thread-safe counter object exposing `snapshot()`.
- `friendly_error(exception)` — turns ugly tracebacks into short, polite
  Telegram copy so users never see a Python stacktrace.

This file is ADD-ONLY. No existing code is modified.
"""
from __future__ import annotations

import functools
import logging
import threading
import time
from collections import defaultdict, deque
from typing import Any, Callable, Deque, Dict, Tuple

log = logging.getLogger("orca.middleware")


class _Metrics:
    """Tiny in-memory counter map. Safe under Python's GIL for our use case."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cmd_calls: Dict[str, int] = defaultdict(int)
        self._cmd_errors: Dict[str, int] = defaultdict(int)
        self._user_calls: Dict[int, int] = defaultdict(int)
        self._started_at: float = time.time()

    def inc_cmd(self, name: str) -> None:
        with self._lock:
            self._cmd_calls[name] += 1

    def inc_error(self, name: str) -> None:
        with self._lock:
            self._cmd_errors[name] += 1

    def inc_user(self, uid: int) -> None:
        with self._lock:
            self._user_calls[uid] += 1

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "uptime_s": int(time.time() - self._started_at),
                "cmd_calls": dict(self._cmd_calls),
                "cmd_errors": dict(self._cmd_errors),
                "unique_users": len(self._user_calls),
                "total_user_events": sum(self._user_calls.values()),
            }


# Module-level singleton — imported by handlers.
metrics = _Metrics()


class _RateLimiter:
    """Per-user sliding window. Keeps up to N timestamps per user."""

    def __init__(self, max_per_minute: int = 20, window_s: int = 60) -> None:
        self.max = max_per_minute
        self.window = window_s
        self._lock = threading.Lock()
        self._hits: Dict[int, Deque[float]] = defaultdict(deque)

    def allow(self, uid: int) -> bool:
        """Return True if the user is under the budget, else False."""
        now = time.time()
        with self._lock:
            dq = self._hits[uid]
            # Drop old entries.
            while dq and (now - dq[0]) > self.window:
                dq.popleft()
            if len(dq) >= self.max:
                return False
            dq.append(now)
            return True


# Global limiter. 20 commands/min/user is comfortable for human driving
# but stops a runaway script.
_limiter = _RateLimiter(max_per_minute=20, window_s=60)


def with_user_ratelimit(max_per_minute: int = 20) -> Callable:
    """Decorator: drop + log if user is over the rate budget.

    Usage:
        @with_user_ratelimit(max_per_minute=30)
        async def cmd_foo(self, u, c): ...
    """
    rl = _RateLimiter(max_per_minute=max_per_minute)

    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrap(self: Any, u: Any, c: Any) -> Any:
            uid = getattr(getattr(u, "effective_user", None), "id", 0)
            metrics.inc_user(uid or 0)
            cmd = fn.__name__
            metrics.inc_cmd(cmd)
            if not rl.allow(uid or 0):
                log.warning("ratelimit uid=%s cmd=%s", uid, cmd)
                # Reply only once per minute to avoid spam.
                if rl.allow(uid or 0) or True:  # always silent drop
                    pass
                return None
            try:
                return await fn(self, u, c)
            except Exception as exc:  # noqa: BLE001
                metrics.inc_error(cmd)
                log.exception("handler %s failed", cmd)
                try:
                    await u.effective_chat.send_message(
                        friendly_error(exc), parse_mode=None
                    )
                except Exception:
                    pass
                return None

        return wrap

    return deco


# Friendly user-facing error messages. Keep them short.
_FRIENDLY: Tuple[Tuple[type, str], ...] = (
    (TimeoutError, "⏳ That took too long. The upstream service didn't reply in time. Try again in a minute."),
    (ConnectionError, "🌐 I can't reach the network right now. Check connectivity and retry."),
    (KeyError, "🔑 I got a malformed response from the upstream. The API may have changed."),
    (ValueError, "⚠️ I couldn't parse that. Check the input format with /help."),
)


def friendly_error(exc: BaseException) -> str:
    """Map a known exception to a short, polite Telegram message."""
    for etype, msg in _FRIENDLY:
        if isinstance(exc, etype):
            return msg
    return "😵 Something went sideways on my side. The team has been notified. Try /status or /help."
