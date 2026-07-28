# android_bridge/adb_controller.py - Unified ADB/Termux Bridge
"""
Single source of truth for Android device control.
- Uses `adb` binary when available
- Falls back to Termux HTTP API on 127.0.0.1:8025
- Exposes both sync (subprocess) and async (Termux-style) interfaces
"""
import subprocess
import asyncio
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional
from loguru import logger
from core.config import config

# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------
def _adb(*args, timeout: int = 10) -> tuple[bool, str, str]:
    """Run an adb command. Returns (ok, stdout, stderr)."""
    cmd = ["adb"]
    if config.ADB_SERIAL != "auto":
        cmd += ["-s", config.ADB_SERIAL]
    cmd += list(args)
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return out.returncode == 0, out.stdout, out.stderr
    except FileNotFoundError:
        return False, "", "adb-not-installed"
    except subprocess.TimeoutExpired:
        return False, "", "timeout"
    except Exception as e:
        return False, "", str(e)

def _termux_api(endpoint: str, timeout: int = 5) -> Optional[str]:
    """Try Termux HTTP API as a fallback."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:8025/{endpoint}", timeout=timeout) as r:
            return r.read().decode()
    except Exception:
        return None

# ------------------------------------------------------------------
# Sync interface (used by Telegram bot)
# ------------------------------------------------------------------
def get_device_info() -> str:
    ok, out, err = _adb("shell", "getprop", "ro.product.model")
    model = out.strip() if ok else "unknown"
    ok2, out2, _ = _adb("shell", "getprop", "ro.build.version.release")
    android_ver = out2.strip() if ok2 else "?"
    ok3, out3, _ = _adb("shell", "getprop", "ro.product.manufacturer")
    manufacturer = out3.strip() if ok3 else "?"
    return f"Model: {manufacturer} {model}\nAndroid: {android_ver}\nADB: {config.ADB_HOST}:{config.ADB_PORT}"

def tap(x: int, y: int) -> dict:
    ok, out, err = _adb("shell", "input", "tap", str(x), str(y))
    return {"ok": ok, "stdout": out, "stderr": err}

def swipe(x1: int, y1: int, x2: int, y2: int, ms: int = 300) -> dict:
    ok, out, err = _adb("shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(ms))
    return {"ok": ok, "stdout": out, "stderr": err}

def text(s: str) -> dict:
    safe = s.replace(" ", "%s")
    ok, out, err = _adb("shell", "input", "text", safe)
    return {"ok": ok, "stdout": out, "stderr": err}

def keyevent(code: int) -> dict:
    ok, out, err = _adb("shell", "input", "keyevent", str(code))
    return {"ok": ok, "stdout": out, "stderr": err}

def screenshot(out_path: str = "/tmp/orca_screen.png") -> dict:
    ok, out, err = _adb("exec-out", "screencap", "-p")
    if ok and out:
        Path(out_path).write_bytes(out.encode("latin-1") if isinstance(out, str) else out.encode())
        return {"ok": True, "path": out_path, "size": len(out)}
    return {"ok": False, "error": err or "screenshot failed"}

def open_app(package: str) -> dict:
    ok, out, err = _adb("shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1")
    return {"ok": ok, "stdout": out, "stderr": err}

def shell(cmd: str, timeout: int = 10) -> dict:
    ok, out, err = _adb("shell", *cmd.split(), timeout=timeout)
    return {"ok": ok, "stdout": out, "stderr": err}

# ------------------------------------------------------------------
# Async interface (Termux-style, for skills/orchestration)
# ------------------------------------------------------------------
async def aexec(command: str, description: Optional[str] = None) -> str:
    """Execute a shell command asynchronously."""
    if description:
        logger.info(f"[adb] {description}: {command}")
    process = await asyncio.create_subprocess_shell(
        command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        msg = f"command failed ({process.returncode}): {stderr.decode().strip()}"
        logger.error(msg)
        return msg
    return stdout.decode().strip()

async def atap(x: int, y: int) -> str:
    return await aexec(f"adb shell input tap {x} {y}", "tap")

async def aswipe(x1: int, y1: int, x2: int, y2: int, duration: int = 300) -> str:
    return await aexec(f"adb shell input swipe {x1} {y1} {x2} {y2} {duration}", "swipe")

async def atext(s: str) -> str:
    safe = s.replace(" ", "%s")
    return await aexec(f'adb shell input text "{safe}"', "text")

async def akey(code: int) -> str:
    return await aexec(f"adb shell input keyevent {code}", "keyevent")
