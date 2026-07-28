# android_bridge/adb_controller.py - ADB / Termux Bridge
"""
Controls Android device over ADB. If ADB is not installed locally,
provides graceful fallback using Termux HTTP API (if reachable).
"""
import subprocess
import json
import urllib.request
import urllib.error
from pathlib import Path
from loguru import logger
from core.config import config

def _adb(*args, timeout=10):
    try:
        out = subprocess.run(
            ["adb", "-s", config.ADB_SERIAL, *args] if config.ADB_SERIAL != "auto" else ["adb", *args],
            capture_output=True, text=True, timeout=timeout,
        )
        return out.returncode == 0, out.stdout, out.stderr
    except FileNotFoundError:
        return False, "", "adb not installed"
    except subprocess.TimeoutExpired:
        return False, "", "timeout"
    except Exception as e:
        return False, "", str(e)

def get_device_info():
    ok, out, err = _adb("shell", "getprop", "ro.product.model")
    if not ok:
        # Try Termux API fallback
        try:
            with urllib.request.urlopen("http://127.0.0.1:8025/api/v1/device", timeout=3) as r:
                return r.read().decode()
        except Exception:
            return f"Device unreachable: {err or 'adb not installed'}"
    model = out.strip()
    ok2, out2, _ = _adb("shell", "getprop", "ro.build.version.release")
    android_ver = out2.strip() if ok2 else "?"
    return f"Model: {model}\nAndroid: {android_ver}\nADB: {config.ADB_HOST}:{config.ADB_PORT}"

def tap(x: int, y: int):
    return _adb("shell", "input", "tap", str(x), str(y))

def swipe(x1, y1, x2, y2, ms=300):
    return _adb("shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(ms))

def text(s: str):
    return _adb("shell", "input", "text", s.replace(" ", "%s"))

def screenshot(out_path: str = "/tmp/screen.png"):
    ok, out, err = _adb("exec-out", "screencap", "-p")
    if ok and out:
        Path = __import__("pathlib").Path
        Path(out_path).write_bytes(out.encode("latin-1") if isinstance(out, str) else out)
        return {"ok": True, "path": out_path}
    return {"ok": False, "error": err}

def open_app(package: str):
    return _adb("shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1")
