"""
Tests for tools/termux_bridge.py - the phone-side daemon.

We test the bits that don't require an actual phone:
  - Config loader
  - HTTP helper (against a fake server)
  - TermuxAPI.execute dispatcher with all subcommands
  - Bridge loop with mocked HTTP
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
DAEMON_PATH = ROOT / "tools" / "termux_bridge.py"


# ---------------------------------------------------------------------
# Module loader
# ---------------------------------------------------------------------
def _load_daemon():
    spec = importlib.util.spec_from_file_location(
        "termux_bridge_under_test", str(DAEMON_PATH))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["termux_bridge_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def daemon():
    return _load_daemon()


# ---------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------
class TestConfig:
    def test_template_creation(self, tmp_path, monkeypatch):
        """If config is missing, the loader creates a template and exits."""
        mod = _load_daemon()
        monkeypatch.setattr(mod, "LOG_DIR", tmp_path)
        monkeypatch.setattr(mod, "CONFIG_PATH", tmp_path / "no_such.json")
        with pytest.raises(SystemExit):
            mod._load_config()
        # Template should now exist
        assert (tmp_path / "no_such.json").exists()
        data = json.loads((tmp_path / "no_such.json").read_text())
        assert "server_url" in data
        assert "auth_token" in data

    def test_loads_existing(self, tmp_path, monkeypatch):
        mod = _load_daemon()
        cfg_path = tmp_path / "termux_bridge.json"
        cfg_path.write_text(json.dumps({
            "server_url": "http://localhost:9999",
            "auth_token": "abc",
            "poll_interval": 1.0,
        }))
        monkeypatch.setattr(mod, "CONFIG_PATH", cfg_path)
        data = mod._load_config()
        assert data["server_url"] == "http://localhost:9999"
        assert data["auth_token"] == "abc"


# ---------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------
class _FakeHandler(BaseHTTPRequestHandler):
    """Echoes back the request body. Records every call."""
    received = []  # type: ignore

    def do_GET(self):  # noqa: N802
        self.received.append(("GET", self.path, self.headers))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "commands": [], "now": 0, "token_hint": "abcd",
        }).encode())

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        self.received.append(("POST", self.path, self.headers, body))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True}).encode())

    def log_message(self, *args, **kwargs):
        pass  # silence the test output


class TestHTTPHelper:
    def test_get_sends_bearer(self, daemon):
        server = HTTPServer(("127.0.0.1", 0), _FakeHandler)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            out = daemon._http_json(
                f"http://127.0.0.1:{port}/pending",
                token="my-token",
            )
            assert out["commands"] == []
            # Inspect the recorded request
            assert len(_FakeHandler.received) == 1
            method, path, headers, *_ = _FakeHandler.received[0]
            assert method == "GET"
            assert path == "/pending"
            assert headers.get("Authorization") == "Bearer my-token"
        finally:
            server.shutdown()
            _FakeHandler.received = []


# ---------------------------------------------------------------------
# TermuxAPI dispatcher
# ---------------------------------------------------------------------
class TestTermuxAPI:
    def test_unknown_subcommand(self, daemon):
        api = daemon.TermuxAPI()
        out = api.execute("nonsense", [])
        assert out["ok"] is False
        assert "unknown subcommand" in out["error"].lower()

    def test_ping_works(self, daemon):
        api = daemon.TermuxAPI()
        out = api.execute("ping", [])
        assert out["ok"] is True
        assert out["result"] == "pong"

    def test_run_with_no_args(self, daemon):
        api = daemon.TermuxAPI()
        out = api.execute("run", [])
        assert out["ok"] is False
        assert "missing command" in out["error"]

    def test_run_with_echo(self, daemon):
        api = daemon.TermuxAPI()
        out = api.execute("run", ["echo", "hello"])
        assert out["ok"] is True
        assert "hello" in out["result"]

    def test_battery_with_mocked_binary(self, daemon):
        """termux-battery-status returns JSON; we mock it."""
        api = daemon.TermuxAPI()
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = json.dumps({
            "percentage": 87, "status": "DISCHARGING", "temperature": 28.4,
        })
        mock_proc.stderr = ""
        with patch("subprocess.run", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/termux-battery-status"):
                with patch.object(api, "has_termux_api", True):
                    out = api.execute("battery", [])
        assert out["ok"] is True
        assert out["result"]["percentage"] == 87
        assert out["result"]["temperature"] == 28.4

    def test_command_not_found(self, daemon):
        api = daemon.TermuxAPI()
        with patch("shutil.which", return_value=None):
            out = api.execute("battery", [])
        assert out["ok"] is False
        assert "termux-api" in out.get("hint", "").lower() or \
               "not found" in out["error"].lower()

    def test_timeout(self, daemon):
        api = daemon.TermuxAPI()
        import subprocess as sp
        with patch("shutil.which", return_value="/usr/bin/termux-wifi-connectioninfo"):
            with patch("subprocess.run",
                        side_effect=sp.TimeoutExpired("x", 5)):
                out = api.execute("wifi", [])
        assert out["ok"] is False
        assert "timeout" in out["error"].lower()

    def test_share_requires_text(self, daemon):
        api = daemon.TermuxAPI()
        out = api.execute("share", [])
        assert out["ok"] is False

    def test_torch_validates_state(self, daemon):
        api = daemon.TermuxAPI()
        out = api.execute("torch", ["sideways"])
        assert out["ok"] is False
        assert "on" in out["error"] and "off" in out["error"]

    def test_notify_with_message(self, daemon):
        api = daemon.TermuxAPI()
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""
        with patch("shutil.which", return_value="/usr/bin/termux-notification"):
            with patch("subprocess.run", return_value=mock_proc):
                out = api.execute("notify", ["Hello", "from", "Orca"])
        assert out["ok"] is True


# ---------------------------------------------------------------------
# Bridge: command dispatch + result posting
# ---------------------------------------------------------------------
class TestBridgeDispatch:
    def test_allowed_command_executes(self, daemon):
        # Mock the API and the HTTP layer
        config = {
            "server_url": "http://localhost:0",
            "auth_token": "t",
            "poll_interval": 0.05,
            "allowed_commands": ["ping", "battery"],
        }
        bridge = daemon.Bridge(config)
        # Capture what gets posted (signature matches daemon: cid, ok, result, error)
        posted = []
        def fake_post(cid, ok=True, result=None, error=""):
            posted.append((cid, ok, result, error))
            return True
        bridge._post_result = fake_post
        # Dispatch a ping
        bridge._handle_command({
            "id": "abc", "subcommand": "ping", "args": [],
        })
        assert len(posted) == 1
        cid, ok, result, err = posted[0]
        assert cid == "abc"
        assert ok is True
        assert result == "pong"

    def test_disallowed_command_rejected(self, daemon):
        config = {
            "server_url": "http://localhost:0",
            "auth_token": "t",
            "poll_interval": 0.05,
            "allowed_commands": ["ping"],
        }
        bridge = daemon.Bridge(config)
        posted = []
        def fake_post(cid, ok=True, result=None, error=""):
            posted.append((cid, ok, result, error))
            return True
        bridge._post_result = fake_post
        bridge._handle_command({
            "id": "xyz", "subcommand": "format", "args": ["/"],
        })
        assert posted[0][1] is False
        assert "allow-list" in posted[0][3]


# ---------------------------------------------------------------------
# Bridge loop with a fake server
# ---------------------------------------------------------------------
class _PollingServer(BaseHTTPRequestHandler):
    """Serves one pending command, then exits after a few requests."""
    request_count = 0
    pending_to_serve = []   # commands the GET endpoint will hand out
    received_posts = []     # bodies the POST endpoint received

    def do_GET(self):  # noqa: N802
        self.__class__.request_count += 1
        if self.__class__.pending_to_serve:
            cmd = self.__class__.pending_to_serve.pop(0)
        else:
            cmd = None
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "commands": [cmd] if cmd else [],
            "now": time.time(),
        }).encode())

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True}).encode())
        # Store the posted result
        try:
            data = json.loads(body)
        except Exception:
            data = {}
        self.__class__.received_posts.append(data)

    def log_message(self, *args, **kwargs):
        pass


class TestBridgeLoop:
    def test_polls_and_answers(self, daemon):
        server = HTTPServer(("127.0.0.1", 0), _PollingServer)
        port = server.server_address[1]
        # Reset server state for a clean run
        _PollingServer.request_count = 0
        _PollingServer.pending_to_serve = [
            {"id": "c1", "subcommand": "ping", "args": []},
        ]
        _PollingServer.received_posts = []
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            config = {
                "server_url": f"http://127.0.0.1:{port}",
                "auth_token": "x",
                "poll_interval": 0.05,
                "event_interval": 999.0,  # don't push health events
                "allowed_commands": ["ping"],
            }
            bridge = daemon.Bridge(config)
            # Run for 0.5s, then stop
            def stop():
                time.sleep(0.5)
                bridge.stop()
            threading.Thread(target=stop, daemon=True).start()
            bridge.run()
        finally:
            server.shutdown()
        # We should have polled at least once
        assert _PollingServer.request_count >= 1, \
            f"server got {_PollingServer.request_count} requests"
        # Find the /result POST (has "id" field) - the daemon may have
        # also pushed a /event health post which doesn't have an "id".
        result_posts = [p for p in _PollingServer.received_posts
                        if "id" in p]
        assert len(result_posts) >= 1, \
            f"server got no /result POSTs (got {_PollingServer.received_posts})"
        assert result_posts[0].get("ok") is True, \
            f"/result POST: {result_posts[0]}"


# ---------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------
class TestCLI:
    def test_doctor_returns_zero_or_one(self, daemon, capsys):
        ret = daemon.cli_doctor()
        assert ret in (0, 1)
        captured = capsys.readouterr()
        assert "Orca Termux Bridge doctor" in captured.out
