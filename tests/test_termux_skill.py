"""
Tests for skills/termux_skill.py - the Telegram command surface.

We mock tools.termux_server so the skill can be tested without
needing the FastAPI app to actually run.
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL_PATH = ROOT / "skills" / "termux_skill.py"


# ---------------------------------------------------------------------
# Module loader (inject a fake termux_server)
# ---------------------------------------------------------------------
def _load_skill():
    """Load skills/termux_skill.py with a mocked termux_server.

    The skill lazy-imports tools.termux_server, so we need to put a
    fake module in sys.modules BEFORE the skill's first call.
    """
    # 1. Create the fake server module
    fake_server = MagicMock()
    fake_server.get_endpoint_url = MagicMock(return_value="http://localhost:8765")
    fake_server.get_token = MagicMock(return_value="fake-token-abc12345xyz")
    fake_server._queue = MagicMock()
    fake_server._queue.stats = MagicMock(return_value={
        "queue_size": 0, "completed_total": 5, "last_poll": time.time(),
    })
    fake_server.push_command = MagicMock(return_value={
        "ok": True, "id": "abc", "result": {"battery": 87},
        "error": "",
    })
    sys.modules["tools"] = MagicMock()
    sys.modules["tools.termux_server"] = fake_server
    # 2. Now load the skill
    spec = importlib.util.spec_from_file_location(
        "termux_skill_under_test", str(SKILL_PATH))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["termux_skill_under_test"] = mod
    spec.loader.exec_module(mod)
    # 3. Reset the lazy loader cache so it picks up our fake
    mod._server = fake_server
    mod._server_load_failed = False
    return mod, fake_server


@pytest.fixture
def skill_pair():
    mod, fake = _load_skill()
    return mod, fake


# ---------------------------------------------------------------------
# SUBCOMMANDS catalogue
# ---------------------------------------------------------------------
class TestSubcommandCatalogue:
    def test_all_expected_subcommands(self, skill_pair):
        mod, _ = skill_pair
        expected = {
            "battery", "wifi", "location", "notify", "toast", "vibrate",
            "speak", "torch", "share", "clipboard", "uptime", "storage",
            "wake", "ping", "run", "status", "setup", "help",
        }
        assert expected.issubset(set(mod.SUBCOMMANDS.keys()))

    def test_each_subcommand_has_timeout(self, skill_pair):
        mod, _ = skill_pair
        for sub, spec in mod.SUBCOMMANDS.items():
            assert "timeout" in spec
            assert spec["timeout"] > 0

    def test_run_has_highest_timeout(self, skill_pair):
        mod, _ = skill_pair
        # `run` is the only subcommand that can be slow
        assert mod.SUBCOMMANDS["run"]["timeout"] >= 20.0


# ---------------------------------------------------------------------
# cmd_termux dispatcher
# ---------------------------------------------------------------------
class TestCmdTermux:
    def test_no_args_returns_help(self, skill_pair):
        mod, _ = skill_pair
        out = mod.cmd_termux([], chat_id=42)
        assert "Orca ↔ Termux Bridge" in out
        assert "/termux battery" in out

    def test_help_subcommand(self, skill_pair):
        mod, _ = skill_pair
        out = mod.cmd_termux(["help"], chat_id=42)
        assert "/termux ping" in out
        assert "/termux battery" in out

    def test_unknown_subcommand(self, skill_pair):
        mod, _ = skill_pair
        out = mod.cmd_termux(["nonsense"], chat_id=42)
        assert "Unknown subcommand" in out

    def test_status_subcommand_local(self, skill_pair):
        mod, fake = skill_pair
        out = mod.cmd_termux(["status"], chat_id=42)
        assert "Bridge Status" in out
        # Should not have called push_command
        fake.push_command.assert_not_called()

    def test_setup_subcommand_local(self, skill_pair):
        mod, fake = skill_pair
        out = mod.cmd_termux(["setup"], chat_id=42)
        assert "Phone Setup" in out
        assert "pkg install python termux-api" in out
        fake.push_command.assert_not_called()

    def test_battery_routes_to_phone(self, skill_pair):
        mod, fake = skill_pair
        out = mod.cmd_termux(["battery"], chat_id=42)
        fake.push_command.assert_called_once()
        args, kwargs = fake.push_command.call_args
        assert kwargs["chat_id"] == 42
        assert kwargs["subcommand"] == "battery"
        assert "battery" in out.lower() or "phone" in out.lower()

    def test_notify_routes_args(self, skill_pair):
        mod, fake = skill_pair
        out = mod.cmd_termux(["notify", "Hello", "from", "Orca"],
                              chat_id=42)
        args, kwargs = fake.push_command.call_args
        assert kwargs["args"] == ["Hello", "from", "Orca"]
        assert kwargs["subcommand"] == "notify"

    def test_run_with_no_args_rejected(self, skill_pair):
        mod, fake = skill_pair
        out = mod.cmd_termux(["run"], chat_id=42)
        assert "needs at least" in out or "missing" in out.lower()
        fake.push_command.assert_not_called()

    def test_run_with_command_routed(self, skill_pair):
        mod, fake = skill_pair
        out = mod.cmd_termux(["run", "ls", "-la"], chat_id=42)
        args, kwargs = fake.push_command.call_args
        assert kwargs["args"] == ["ls", "-la"]

    def test_phone_timeout_message(self, skill_pair):
        mod, fake = skill_pair
        fake.push_command.return_value = {
            "ok": False, "id": "abc", "result": None,
            "error": "timeout: phone did not answer in 5.0s",
            "status": "pending",
        }
        out = mod.cmd_termux(["battery"], chat_id=42)
        assert "didn't answer" in out or "timeout" in out.lower()
        assert "nohup python termux_bridge.py" in out

    def test_phone_error_with_hint(self, skill_pair):
        mod, fake = skill_pair
        fake.push_command.return_value = {
            "ok": False, "id": "abc", "result": None,
            "error": "command not found: termux-battery-status",
        }
        out = mod.cmd_termux(["battery"], chat_id=42)
        assert "failed" in out
        assert "termux-api" in out.lower()

    def test_phone_success_dict_result(self, skill_pair):
        mod, fake = skill_pair
        fake.push_command.return_value = {
            "ok": True, "id": "abc",
            "result": {"percentage": 87, "status": "DISCHARGING"},
        }
        out = mod.cmd_termux(["battery"], chat_id=42)
        assert "87" in out
        assert "DISCHARGING" in out
        assert "json" in out.lower()

    def test_phone_success_string_result(self, skill_pair):
        mod, fake = skill_pair
        fake.push_command.return_value = {
            "ok": True, "id": "abc",
            "result": "Filesystem      Size  Used Avail Use% Mounted on\n...",
        }
        out = mod.cmd_termux(["storage"], chat_id=42)
        assert "Filesystem" in out

    def test_push_command_exception_caught(self, skill_pair):
        mod, fake = skill_pair
        fake.push_command.side_effect = RuntimeError("server unreachable")
        out = mod.cmd_termux(["battery"], chat_id=42)
        assert "Bridge error" in out
        assert "RuntimeError" in out

    def test_battery_with_extra_args_rejected(self, skill_pair):
        mod, fake = skill_pair
        out = mod.cmd_termux(["battery", "extra", "stuff"], chat_id=42)
        assert "no arguments" in out


# ---------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------
class TestFormatting:
    def test_truncate_short_string_unchanged(self, skill_pair):
        mod, _ = skill_pair
        assert mod._truncate("hi") == "hi"

    def test_truncate_long_string(self, skill_pair):
        mod, _ = skill_pair
        long_text = "x" * 5000
        out = mod._truncate(long_text)
        assert len(out) < len(long_text)
        assert "truncated" in out.lower()

    def test_format_success_with_dict(self, skill_pair):
        mod, _ = skill_pair
        out = mod._format_success("battery",
                                   {"ok": True, "result": {"x": 1}},
                                   elapsed_ms=250.0)
        assert "battery" in out
        assert "0.25" in out or "0.2" in out  # 250ms

    def test_format_error_with_termux_api_hint(self, skill_pair):
        mod, _ = skill_pair
        out = mod._format_error("battery",
                                 {"ok": False,
                                  "error": "termux-battery-status: not found"})
        assert "termux-api" in out

    def test_format_error_with_network_hint(self, skill_pair):
        mod, _ = skill_pair
        out = mod._format_error("wifi",
                                 {"ok": False, "error": "connection refused"})
        assert "internet" in out.lower() or "network" in out.lower()


# ---------------------------------------------------------------------
# Skill card
# ---------------------------------------------------------------------
class TestSkillCard:
    def test_skill_card_shape(self, skill_pair):
        mod, _ = skill_pair
        card = mod.skill_card()
        assert card["name"] == "termux"
        assert "title" in card
        assert "summary" in card
        assert "commands" in card
        assert any("/termux" in c for c in card["commands"])


# ---------------------------------------------------------------------
# Server missing (load failure path)
# ---------------------------------------------------------------------
class TestServerMissing:
    def test_graceful_when_server_returns_none(self, skill_pair):
        """If the server module is not loaded, skill should say so.

        We simulate this by setting _server_load_failed=True and
        clearing the _server cache, so the next _get_server() call
        returns None.
        """
        mod, fake = skill_pair
        # Force the lazy loader to "fail"
        mod._server = None
        mod._server_load_failed = True
        out = mod.cmd_termux(["battery"], chat_id=42)
        assert isinstance(out, str)
        assert "bridge server failed to load" in out.lower() or \
               "fastapi" in out.lower()
