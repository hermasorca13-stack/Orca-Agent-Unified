"""
Tests for tools/termux_server.py - the Orca-side HTTP bridge.

Strategy: use FastAPI's TestClient to drive the endpoints. We
override TERMUX_BRIDGE_TOKEN so we know what to send. The queue
file is patched to a tmp path per test so nothing leaks between
runs.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL_PATH = ROOT / "tools" / "termux_server.py"


# ---------------------------------------------------------------------
# Module loader (env must be set BEFORE import so the module picks
# up our overrides for TOKEN and QUEUE_PATH).
# ---------------------------------------------------------------------
def _load_server(tmp_path, token="test-token-12345"):
    os.environ["TERMUX_BRIDGE_TOKEN"] = token
    os.environ["TERMUX_BRIDGE_QUEUE"] = str(tmp_path / "queue.jsonl")
    os.environ["TERMUX_BRIDGE_MAX_QUEUE"] = "50"
    os.environ["TERMUX_BRIDGE_RESULT_TTL"] = "60"
    spec = importlib.util.spec_from_file_location(
        "termux_server_under_test", str(SKILL_PATH))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["termux_server_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------
@pytest.fixture
def server(tmp_path):
    mod = _load_server(tmp_path)
    # Reset module-level singletons so each test starts clean.
    mod._queue = mod._Queue(mod.QUEUE_PATH)
    mod._events = mod._EventLog(mod.QUEUE_PATH.parent / "events.jsonl")
    # Replace the FastAPI app's dependency for the test client.
    from fastapi.testclient import TestClient
    client = TestClient(mod.app)
    client.HDR = {"Authorization": f"Bearer test-token-12345"}
    return mod, client


# ---------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------
class TestHealth:
    def test_health_no_auth_required(self, server):
        mod, client = server
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["ok"] is True


# ---------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------
class TestAuth:
    def test_missing_authorization_header(self, server):
        _, client = server
        r = client.get("/pending")
        assert r.status_code == 401

    def test_wrong_scheme(self, server):
        _, client = server
        r = client.get("/pending", headers={"Authorization": "Basic abc"})
        assert r.status_code == 401

    def test_wrong_token(self, server):
        _, client = server
        r = client.get("/pending", headers={"Authorization": "Bearer wrong"})
        assert r.status_code == 401

    def test_correct_token(self, server):
        _, client = server
        r = client.get("/pending", headers=client.HDR)
        assert r.status_code == 200


# ---------------------------------------------------------------------
# /pending
# ---------------------------------------------------------------------
class TestPending:
    def test_empty_queue(self, server):
        _, client = server
        r = client.get("/pending", headers=client.HDR)
        assert r.status_code == 200
        body = r.json()
        assert body["commands"] == []
        assert "now" in body
        assert "token_hint" in body

    def test_returns_enqueued_commands(self, server):
        mod, client = server
        # Manually enqueue (bypasses the /command HTTP endpoint)
        entry = mod._queue.enqueue(chat_id=42, subcommand="battery", args=[])
        r = client.get("/pending", headers=client.HDR)
        assert r.status_code == 200
        cmds = r.json()["commands"]
        assert len(cmds) == 1
        assert cmds[0]["id"] == entry["id"]
        assert cmds[0]["subcommand"] == "battery"

    def test_since_filter_excludes_old(self, server):
        mod, client = server
        mod._queue.enqueue(chat_id=1, subcommand="ping", args=[])
        # Set since to the future, so no commands should be returned
        r = client.get(f"/pending?since={time.time() + 100}",
                       headers=client.HDR)
        assert r.json()["commands"] == []


# ---------------------------------------------------------------------
# /command
# ---------------------------------------------------------------------
class TestCommand:
    def test_enqueue_new(self, server):
        _, client = server
        r = client.post("/command",
                          headers=client.HDR,
                          json={"chat_id": 100, "subcommand": "battery",
                                "args": []})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert "id" in body

    def test_validation(self, server):
        _, client = server
        r = client.post("/command",
                          headers=client.HDR,
                          json={"chat_id": 0, "subcommand": "x", "args": []})
        assert r.status_code == 422

    def test_queue_full(self, tmp_path):
        mod = _load_server(tmp_path)
        mod.QUEUE_PATH = tmp_path / "queue.jsonl"
        mod.MAX_QUEUE_SIZE = 2
        mod._queue = mod._Queue(mod.QUEUE_PATH)
        from fastapi.testclient import TestClient
        client = TestClient(mod.app)
        hdr = {"Authorization": f"Bearer test-token-12345"}
        # Fill the queue
        for i in range(2):
            r = client.post("/command", headers=hdr,
                             json={"chat_id": 1, "subcommand": "ping",
                                   "args": []})
            assert r.status_code == 200
        # Next one should 503
        r = client.post("/command", headers=hdr,
                         json={"chat_id": 1, "subcommand": "ping",
                               "args": []})
        assert r.status_code == 503


# ---------------------------------------------------------------------
# /result
# ---------------------------------------------------------------------
class TestResult:
    def test_post_and_fetch(self, server):
        mod, client = server
        e = mod._queue.enqueue(chat_id=42, subcommand="battery", args=[])
        # Phone posts the result
        r = client.post("/result", headers=client.HDR,
                         json={"id": e["id"], "ok": True,
                               "result": {"battery": 87}})
        assert r.status_code == 200
        # Bot fetches the result
        r = client.get(f"/result/{e['id']}", headers=client.HDR)
        body = r.json()
        assert body["status"] == "completed"
        assert body["ok"] is True
        assert body["result"] == {"battery": 87}

    def test_post_failure_marks_error(self, server):
        mod, client = server
        e = mod._queue.enqueue(chat_id=42, subcommand="run", args=[])
        r = client.post("/result", headers=client.HDR,
                         json={"id": e["id"], "ok": False,
                               "error": "permission denied"})
        assert r.status_code == 200
        r = client.get(f"/result/{e['id']}", headers=client.HDR)
        body = r.json()
        assert body["ok"] is False
        assert body["error"] == "permission denied"

    def test_unknown_id(self, server):
        _, client = server
        r = client.post("/result", headers=client.HDR,
                         json={"id": "nonexistent", "ok": True,
                               "result": None})
        assert r.status_code == 404


# ---------------------------------------------------------------------
# /event
# ---------------------------------------------------------------------
class TestEvent:
    def test_push_and_list(self, server):
        _, client = server
        r = client.post("/event", headers=client.HDR,
                         json={"kind": "battery",
                               "data": {"level": 87, "charging": False},
                               "chat_id": 42})
        assert r.status_code == 200
        body = r.json()
        assert body["kind"] == "battery"
        assert body["data"]["level"] == 87
        # List
        r = client.get("/events", headers=client.HDR)
        evs = r.json()["events"]
        assert len(evs) == 1
        assert evs[0]["kind"] == "battery"


# ---------------------------------------------------------------------
# /status
# ---------------------------------------------------------------------
class TestStatus:
    def test_status_initial(self, server):
        _, client = server
        r = client.get("/status", headers=client.HDR)
        body = r.json()
        assert body["service"] == "orca-termux-bridge"
        assert body["queue"]["queue_size"] == 0
        assert body["queue"]["completed_total"] == 0


# ---------------------------------------------------------------------
# push_command (sync helper, used by the bot)
# ---------------------------------------------------------------------
class TestPushCommand:
    def test_round_trip(self, server):
        """Enqueue, simulate the phone answering, return value matches."""
        mod, _ = server
        # Capture the id push_command creates
        captured = {}
        original_enqueue = mod._queue.enqueue

        def enqueue_capture(chat_id, subcommand, args):
            entry = original_enqueue(chat_id, subcommand, args)
            captured["id"] = entry["id"]
            return entry
        mod._queue.enqueue = enqueue_capture

        # In another thread (simulated): phone answers
        def _answer():
            time.sleep(0.1)
            if "id" in captured:
                mod._queue.complete(captured["id"], ok=True,
                                    result={"battery": 87})
        import threading
        t = threading.Thread(target=_answer, daemon=True)
        t.start()
        result = mod.push_command(chat_id=99, subcommand="battery",
                                   args=[], timeout=2.0)
        t.join()
        assert result["ok"] is True
        assert result["result"] == {"battery": 87}

    def test_timeout(self, server):
        """No phone answer -> ok=False with timeout message."""
        mod, _ = server
        result = mod.push_command(chat_id=99, subcommand="battery",
                                   args=[], timeout=0.5)
        assert result["ok"] is False
        assert "timeout" in result["error"].lower()


# ---------------------------------------------------------------------
# Pruning
# ---------------------------------------------------------------------
class TestPruning:
    def test_old_completed_entries_pruned(self, server):
        mod, _ = server
        e = mod._queue.enqueue(chat_id=1, subcommand="x", args=[])
        mod._queue.complete(e["id"], ok=True, result=None)
        # Force the entry to look old
        entries = mod._queue._read_all()
        for entry in entries:
            entry["completed_at"] = time.time() - 99999
        mod._queue._write_all(entries)
        # Wait a tick
        time.sleep(0.05)
        # Prune
        removed = mod._queue.prune()
        assert removed >= 1
        # And the entry is gone
        assert mod._queue.get_result(e["id"]) is None
