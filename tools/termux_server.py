"""
tools/termux_server.py - Orca-side HTTP bridge for the Termux daemon.

This is the half of the Orca<->Termux bridge that lives on the Orca
side. The phone runs `tools/termux_bridge.py` (the daemon); this
server accepts its HTTP calls and feeds commands from the Telegram
bot through to the phone.

Endpoints (all require Authorization: Bearer <TERMUX_BRIDGE_TOKEN>):

  GET  /pending?since=<ts>  -> {"commands": [...]}
                              Returns pending commands for the phone.
  POST /result              <- {"id": "...", "ok": true, "result": ...}
                              Phone posts the output of a command.
  POST /event               <- {"kind": "battery", "data": {...}}
                              Spontaneous event push from the phone.
  GET  /status              -> {"queue_size": N, "last_poll": ts, ...}
                              Server health (used by /termux status).
  POST /command             <- {"chat_id": 12345, "subcommand": "battery",
                                 "args": [...]}
                              Internal: bot pushes a new command.
  GET  /result/{id}         -> {"status": "completed", "result": ...}
                              Bot polls for the result of its command.

Transport: HTTP polling, default port 8765, no WebSocket.

Run standalone:
    python -m tools.termux_server
    # or
    uvicorn tools.termux_server:app --host 0.0.0.0 --port 8765
"""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from loguru import logger

try:
    from pydantic import BaseModel, Field  # v2 (FastAPI 0.110+)
except Exception:  # pragma: no cover - FastAPI ships pydantic
    from pydantic import BaseModel, Field  # type: ignore


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------
def _project_root() -> Path:
    """Project root = parent of this file's parent (tools/ lives there)."""
    return Path(__file__).resolve().parent.parent


ROOT = _project_root()
QUEUE_PATH = Path(os.getenv("TERMUX_BRIDGE_QUEUE", str(ROOT / "data" / "termux_queue.jsonl")))
DEFAULT_TOKEN = secrets.token_urlsafe(24)  # if no token in env, generate one
TOKEN = os.getenv("TERMUX_BRIDGE_TOKEN", "").strip() or DEFAULT_TOKEN
PORT = int(os.getenv("TERMUX_BRIDGE_PORT", "8765"))
HOST = os.getenv("TERMUX_BRIDGE_HOST", "0.0.0.0")
RESULT_TTL_SECONDS = int(os.getenv("TERMUX_BRIDGE_RESULT_TTL", "300"))  # 5 min
MAX_QUEUE_SIZE = int(os.getenv("TERMUX_BRIDGE_MAX_QUEUE", "200"))
MAX_OUTPUT_BYTES = int(os.getenv("TERMUX_BRIDGE_MAX_OUTPUT", "4096"))

# Ensure data dir exists
QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------
# Queue (file-based JSONL, thread-safe)
# ---------------------------------------------------------------------
class _Queue:
    """File-backed command/result queue.

    Each line is one entry. The phone reads /pending (status=pending)
    and posts /result, which flips the entry to status=completed.
    Entries older than RESULT_TTL_SECONDS are pruned on each access.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = Lock()
        # Create the file if missing
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")

    def _read_all(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        try:
            with self.path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except FileNotFoundError:
            pass
        return out

    def _write_all(self, entries: List[Dict[str, Any]]) -> None:
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        tmp.replace(self.path)

    def prune(self) -> int:
        """Drop entries older than TTL. Returns count removed."""
        with self._lock:
            now = time.time()
            entries = self._read_all()
            before = len(entries)
            entries = [
                e for e in entries
                if e.get("status") == "pending"
                or now - float(e.get("completed_at", e.get("created_at", 0))) < RESULT_TTL_SECONDS
            ]
            if len(entries) != before:
                self._write_all(entries)
            return before - len(entries)

    def enqueue(self, chat_id: int, subcommand: str, args: List[str]) -> Dict[str, Any]:
        """Push a new command. Returns the queued entry."""
        with self._lock:
            entries = self._read_all()
            pending = [e for e in entries if e.get("status") == "pending"]
            if len(pending) >= MAX_QUEUE_SIZE:
                raise HTTPException(
                    status_code=503,
                    detail=f"queue full ({MAX_QUEUE_SIZE} pending). try again later.",
                )
            entry = {
                "id": uuid.uuid4().hex[:12],
                "chat_id": int(chat_id),
                "subcommand": str(subcommand),
                "args": [str(a) for a in args],
                "created_at": time.time(),
                "status": "pending",
                "result": None,
            }
            entries.append(entry)
            self._write_all(entries)
            logger.info("termux_queue: enqueue id={} sub={} chat={}",
                        entry["id"], subcommand, chat_id)
            return entry

    def get_pending(self, since: float = 0.0) -> List[Dict[str, Any]]:
        """Return pending commands newer than `since` (epoch seconds)."""
        with self._lock:
            entries = self._read_all()
        return [
            e for e in entries
            if e.get("status") == "pending" and float(e.get("created_at", 0)) > since
        ]

    def get_result(self, cmd_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            entries = self._read_all()
        for e in entries:
            if e.get("id") == cmd_id:
                return e
        return None

    def complete(self, cmd_id: str, ok: bool, result: Any, error: str = "") -> bool:
        """Mark a command complete. Returns True if the entry was found."""
        with self._lock:
            entries = self._read_all()
            for e in entries:
                if e.get("id") == cmd_id:
                    e["status"] = "completed"
                    e["ok"] = bool(ok)
                    e["completed_at"] = time.time()
                    if ok:
                        e["result"] = result
                        e["error"] = ""
                    else:
                        e["result"] = None
                        e["error"] = str(error or "unknown error")[:500]
                    self._write_all(entries)
                    logger.info("termux_queue: complete id={} ok={}", cmd_id, ok)
                    return True
        return False

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            entries = self._read_all()
        pending = [e for e in entries if e.get("status") == "pending"]
        completed = [e for e in entries if e.get("status") == "completed"]
        last_poll = max(
            (float(e.get("completed_at", 0)) for e in completed),
            default=0.0,
        )
        return {
            "queue_size": len(pending),
            "completed_total": len(completed),
            "last_poll": last_poll,
        }


# ---------------------------------------------------------------------
# Event log (in-memory, capped). Phone-initiated events (battery, etc.)
# ---------------------------------------------------------------------
class _EventLog:
    """Spontaneous events from the phone. Kept in memory and
    file-backed for restart-safety. Capped at 200 entries."""

    MAX = 200

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._events: List[Dict[str, Any]] = self._load()

    def _load(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            return [json.loads(l) for l in self.path.read_text(encoding="utf-8").splitlines() if l.strip()]
        except Exception:
            return []

    def _persist(self) -> None:
        with self.path.open("w", encoding="utf-8") as f:
            for e in self._events[-self.MAX:]:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")

    def push(self, kind: str, data: Dict[str, Any], chat_id: Optional[int] = None) -> Dict[str, Any]:
        with self._lock:
            ev = {
                "id": uuid.uuid4().hex[:12],
                "kind": str(kind),
                "data": data,
                "ts": time.time(),
                "chat_id": chat_id,
            }
            self._events.append(ev)
            self._events = self._events[-self.MAX:]
            self._persist()
            logger.info("termux_event: kind={} chat={}", kind, chat_id)
            return ev

    def list(self, since: float = 0.0, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            evs = list(self._events)
        out = [e for e in evs if float(e.get("ts", 0)) > since]
        if kind:
            out = [e for e in out if e.get("kind") == kind]
        return out


# ---------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------
class CommandRequest(BaseModel):
    chat_id: int = Field(..., ge=1)
    subcommand: str = Field(..., min_length=1, max_length=64)
    args: List[str] = Field(default_factory=list)


class ResultRequest(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    ok: bool = True
    result: Any = None
    error: str = ""


class EventRequest(BaseModel):
    kind: str = Field(..., min_length=1, max_length=64)
    data: Dict[str, Any] = Field(default_factory=dict)
    chat_id: Optional[int] = None


# ---------------------------------------------------------------------
# FastAPI app + auth dependency
# ---------------------------------------------------------------------
_queue = _Queue(QUEUE_PATH)
_events = _EventLog(QUEUE_PATH.parent / "termux_events.jsonl")


def _check_auth(authorization: Optional[str] = Header(None)) -> None:
    """Verify the bearer token. Constant-time-ish compare via secrets."""
    if not authorization:
        raise HTTPException(status_code=401, detail="missing Authorization header")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="invalid Authorization scheme")
    token = authorization.split(" ", 1)[1].strip()
    if not secrets.compare_digest(token, TOKEN):
        raise HTTPException(status_code=401, detail="invalid token")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("termux_server: starting on {}:{} (queue={})", HOST, PORT, QUEUE_PATH)
    logger.info("termux_server: token = {}...{}", TOKEN[:6], TOKEN[-4:])
    yield
    logger.info("termux_server: shutting down")


app = FastAPI(
    title="Orca Termux Bridge",
    description="HTTP bridge between the Orca Telegram bot and a phone running Termux.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> Dict[str, Any]:
    """Unauthenticated health check (for load balancers)."""
    return {"ok": True, "service": "orca-termux-bridge"}


@app.get("/pending")
async def get_pending(
    since: float = Query(0.0, ge=0.0),
    _: None = Depends(_check_auth),
) -> Dict[str, Any]:
    """Phone polls this to get new commands. `since` is the last-seen
    epoch timestamp; only commands newer than that are returned."""
    _queue.prune()
    cmds = _queue.get_pending(since=since)
    return {
        "commands": cmds[:20],  # cap at 20 per poll
        "now": time.time(),
        "token_hint": TOKEN[:4],  # tiny echo so the phone knows it's talking to the right server
    }


class _CommandResult(BaseModel):
    id: str
    ok: bool
    result: Any = None
    error: str = ""


@app.post("/result")
async def post_result(
    body: ResultRequest,
    _: None = Depends(_check_auth),
) -> Dict[str, Any]:
    """Phone posts the result of a previously-polled command."""
    found = _queue.complete(body.id, ok=body.ok, result=body.result, error=body.error)
    if not found:
        raise HTTPException(status_code=404, detail=f"unknown command id: {body.id}")
    return {"ok": True, "id": body.id}


@app.post("/event")
async def post_event(
    body: EventRequest,
    _: None = Depends(_check_auth),
) -> Dict[str, Any]:
    """Phone posts a spontaneous event (battery low, location update, ...)."""
    return _events.push(body.kind, body.data, body.chat_id)


@app.get("/events")
async def list_events(
    since: float = Query(0.0, ge=0.0),
    kind: Optional[str] = Query(None),
    _: None = Depends(_check_auth),
) -> Dict[str, Any]:
    """List recent events, optionally filtered by `since` and `kind`."""
    return {"events": _events.list(since=since, kind=kind)[:50]}


@app.get("/status")
async def get_status(_: None = Depends(_check_auth)) -> Dict[str, Any]:
    """Server health: queue size, last poll timestamp, etc."""
    return {
        "queue": _queue.stats(),
        "events": len(_events.list()),
        "service": "orca-termux-bridge",
        "now": time.time(),
    }


@app.post("/command")
async def post_command(
    body: CommandRequest,
    _: None = Depends(_check_auth),
) -> Dict[str, Any]:
    """Bot pushes a new command to the queue. Phone picks it up on
    its next /pending poll."""
    entry = _queue.enqueue(body.chat_id, body.subcommand, body.args)
    return {"ok": True, "id": entry["id"]}


@app.get("/result/{cmd_id}")
async def get_command_result(
    cmd_id: str,
    _: None = Depends(_check_auth),
) -> Dict[str, Any]:
    """Bot polls this to check if its command has been answered."""
    entry = _queue.get_result(cmd_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"unknown command id: {cmd_id}")
    return {
        "id": entry.get("id"),
        "status": entry.get("status"),
        "ok": entry.get("ok"),
        "result": entry.get("result"),
        "error": entry.get("error", ""),
        "completed_at": entry.get("completed_at"),
    }


# ---------------------------------------------------------------------
# Convenience helpers for the bot (not HTTP endpoints - import-only)
# ---------------------------------------------------------------------
def push_command(chat_id: int, subcommand: str, args: Optional[List[str]] = None,
                 timeout: float = 15.0, poll_interval: float = 0.5) -> Dict[str, Any]:
    """Push a command and wait for the phone to answer.

    Used by skills/termux_skill.py. The function blocks (with polling)
    until the phone responds, the timeout elapses, or the queue is
    pruned. Returns a dict with at least {ok, result|error}.

    This is a synchronous helper (not async) because the bot is
    currently sync at the handler level.
    """
    args = list(args or [])
    entry = _queue.enqueue(chat_id, subcommand, args)
    cmd_id = entry["id"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(poll_interval)
        r = _queue.get_result(cmd_id)
        if r and r.get("status") == "completed":
            return {
                "ok": bool(r.get("ok")),
                "id": cmd_id,
                "result": r.get("result"),
                "error": r.get("error", ""),
            }
    # Timed out - leave the entry in the queue for the next poll
    return {
        "ok": False,
        "id": cmd_id,
        "result": None,
        "error": f"timeout: phone did not answer in {timeout:.1f}s",
        "status": "pending",
    }


def get_token() -> str:
    """Return the current auth token (for the bot to display in /termux setup)."""
    return TOKEN


def get_endpoint_url() -> str:
    """Best-effort public URL hint for the user."""
    return f"http://{HOST}:{PORT}"


# ---------------------------------------------------------------------
# Standalone runner: `python -m tools.termux_server`
# ---------------------------------------------------------------------
def main() -> None:  # pragma: no cover
    import uvicorn
    print(f"Orca Termux Bridge - listening on {HOST}:{PORT}")
    print(f"Queue file:    {QUEUE_PATH}")
    print(f"Auth token:    {TOKEN[:6]}...{TOKEN[-4:]}")
    print(f"  (full token in env TERMUX_BRIDGE_TOKEN or printed above)")
    print(f"  curl http://localhost:{PORT}/health")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":  # pragma: no cover
    main()
