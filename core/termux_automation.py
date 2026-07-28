"""
core/termux_automation.py
=========================
Termux & Android automation skills (ADB bridge).

This module is added to satisfy the import in core/skills.py at line 712.
It uses the existing android_bridge.adb_controller when available and falls
back to a safe dry-run with informative output.

Methods expected by SkillRegistry:
  - execute_termux_command(command, description=None)
  - adb_command(command)
  - adb_tap(x, y)
  - adb_swipe(x1, y1, x2, y2, duration)
  - adb_text(text)
  - adb_keyevent(keycode)
  - adb_screenshot()
  - termux_api_call(api_command, *args)
"""
from __future__ import annotations
import asyncio
import shutil
import subprocess
from typing import Optional, List

try:
    from android_bridge.adb_controller import (
        adb_shell, tap as adb_tap_native, swipe as adb_swipe_native,
        text as adb_text_native, keyevent as adb_keyevent_native,
        get_device_info,
    )
    _ADB_AVAILABLE = True
except Exception:  # pragma: no cover
    _ADB_AVAILABLE = False


def _run_local(cmd: str, timeout: int = 30) -> dict:
    """Run a local shell command (Termux side). Returns a small dict."""
    try:
        completed = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return {
            "ok": completed.returncode == 0,
            "stdout": (completed.stdout or "")[:2000],
            "stderr": (completed.stderr or "")[:500],
            "returncode": completed.returncode,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "stdout": "", "stderr": ""}


class TermuxAutomationSkills:
    """Wraps Termux / ADB operations. Safe fallback when no device is attached."""

    def __init__(self):
        self.adb_bin = shutil.which("adb") or "adb"
        self.connected = self._check_device()

    def _check_device(self) -> bool:
        if not _ADB_AVAILABLE:
            return False
        try:
            info = get_device_info() or {}
            return bool(info.get("connected"))
        except Exception:
            return False

    async def execute_termux_command(self, command: str, description: Optional[str] = None) -> str:
        """Run a shell command in the Termux environment."""
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(None, _run_local, command, 60)
        if r.get("ok"):
            head = f"💻 $ {command}\n" + (f"({description})\n" if description else "")
            return head + (r.get("stdout") or "(no output)")
        return f"❌ $ {command} → rc={r.get('returncode')}\n{r.get('stderr') or r.get('error','')}"

    async def adb_command(self, command: str) -> str:
        """Run a raw ADB shell command."""
        if not self.connected or not _ADB_AVAILABLE:
            return f"⚠️ No ADB device connected. (Would run: adb shell {command})"
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(None, _run_local, f"{self.adb_bin} shell {command}", 30)
        return r.get("stdout") or f"(empty) {r.get('stderr','')}"

    async def adb_tap(self, x: int, y: int) -> str:
        if not self.connected or not _ADB_AVAILABLE:
            return f"⚠️ No device. (Would tap {x},{y})"
        r = adb_tap_native(int(x), int(y))
        return f"{'✅' if r.get('ok') else '❌'} tap {x},{y}"

    async def adb_swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300) -> str:
        if not self.connected or not _ADB_AVAILABLE:
            return f"⚠️ No device. (Would swipe {x1},{y1}→{x2},{y2} in {duration}ms)"
        r = adb_swipe_native(int(x1), int(y1), int(x2), int(y2), int(duration))
        return f"{'✅' if r.get('ok') else '❌'} swipe {x1},{y1}→{x2},{y2}"

    async def adb_text(self, text: str) -> str:
        if not self.connected or not _ADB_AVAILABLE:
            return f"⚠️ No device. (Would type: {text[:50]})"
        r = adb_text_native(text)
        return f"{'✅' if r.get('ok') else '❌'} text"

    async def adb_keyevent(self, keycode: int) -> str:
        if not self.connected or not _ADB_AVAILABLE:
            return f"⚠️ No device. (Would keyevent {keycode})"
        r = adb_keyevent_native(int(keycode))
        return f"{'✅' if r.get('ok') else '❌'} keyevent {keycode}"

    async def adb_screenshot(self) -> str:
        if not self.connected or not _ADB_AVAILABLE:
            return "⚠️ No device. (Would screenshot)"
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(None, _run_local, f"{self.adb_bin} exec-out screencap -p", 30)
        if r.get("ok"):
            return f"📸 screenshot captured ({len(r.get('stdout') or '')} bytes)"
        return f"❌ screenshot failed: {r.get('stderr','')}"

    async def termux_api_call(self, api_command: str, *args) -> str:
        """Generic Termux:API call (requires termux-api package)."""
        if not shutil.which("termux-" + api_command.split()[0] if api_command else "termux-"):
            return f"⚠️ termux-api not installed. (Would call: termux-{api_command} {' '.join(args)})"
        cmd = f"termux-{api_command} " + " ".join(str(a) for a in args)
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(None, _run_local, cmd, 30)
        return r.get("stdout") or f"(empty) {r.get('stderr','')}"
