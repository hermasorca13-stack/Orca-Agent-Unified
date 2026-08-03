"""
tools/termux_bridge.py - Phone-side daemon for the Orca bridge.

This is the half of the Orca<->Termux bridge that lives on the phone.
Run it inside Termux on Android:

    pkg install python termux-api
    mkdir -p ~/orca_bridge
    cd ~/orca_bridge
    # Copy this file + termux_bridge.json from the Orca repo
    nohup python termux_bridge.py &

The daemon:

  1. Polls Orca /pending every POLL_INTERVAL seconds
  2. For each pending command, executes via Termux:API or shell
  3. Posts the result to Orca /result
  4. Periodically posts health events to Orca /event
  5. Auto-reconnects on network failure (exponential backoff)
  6. Logs to ~/orca_bridge/bridge.log

Configuration (termux_bridge.json in the same dir):

  {
    "server_url": "http://your-orca-host:8765",
    "auth_token": "the token from TERMUX_BRIDGE_TOKEN",
    "device_name": "my-pixel-7",
    "poll_interval": 3.0,
    "event_interval": 300.0,
    "allowed_commands": ["battery", "wifi", "location", "run",
                          "notify", "vibrate", "toast", "clipboard",
                          "speak", "torch", "share", "uptime",
                          "storage", "wake", "ping"]
  }

No external Python deps - stdlib only. This script must run in
Termux, not on a server (Termux:API commands are Android-only).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------
APP_NAME = "orca-bridge"
APP_VERSION = "1.0.0"
DEFAULT_POLL = 3.0
DEFAULT_EVENT = 300.0  # 5 min
LOG_DIR = Path.home() / "orca_bridge"
LOG_FILE = LOG_DIR / "bridge.log"
CONFIG_PATH = LOG_DIR / "termux_bridge.json"
ALLOWED_DEFAULT = [
    "battery", "wifi", "location", "run", "notify", "vibrate",
    "toast", "clipboard", "speak", "torch", "share", "uptime",
    "storage", "wake", "ping",
]


# ---------------------------------------------------------------------
# Logging (file + stderr, no loguru dep on the phone)
# ---------------------------------------------------------------------
def _log(msg: str, level: str = "INFO") -> None:
    """Append a timestamped line to LOG_FILE + stderr."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        line = f"{datetime.now().isoformat(timespec='seconds')} {level} {msg}"
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, file=sys.stderr, flush=True)


# ---------------------------------------------------------------------
# HTTP helpers (stdlib only)
# ---------------------------------------------------------------------
def _http_json(url: str, method: str = "GET", body: Optional[Dict[str, Any]] = None,
               token: str = "", timeout: float = 10.0) -> Dict[str, Any]:
    """Make an HTTP request. Returns the parsed JSON or raises."""
    data = None
    headers = {
        "User-Agent": f"Orca-Termux-Bridge/{APP_VERSION}",
        "Accept": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore"))


# ---------------------------------------------------------------------
# Termux:API command execution
# ---------------------------------------------------------------------
class TermuxAPI:
    """Run a subcommand via Termux:API or shell. Every method returns
    a dict with {ok, result|error, hint?}."""

    def __init__(self) -> None:
        self.has_termux_api = shutil.which("termux-battery-status") is not None

    def _run(self, *args: str, timeout: float = 10.0) -> Dict[str, Any]:
        """Run a Termux:API helper, capture JSON if possible."""
        if not args:
            return {"ok": False, "error": "no command"}
        bin_path = shutil.which(args[0])
        if not bin_path:
            return {
                "ok": False,
                "error": f"command not found: {args[0]}",
                "hint": "pkg install termux-api",
            }
        try:
            proc = subprocess.run(
                list(args),
                capture_output=True, text=True, timeout=timeout,
            )
            if proc.returncode != 0:
                return {
                    "ok": False,
                    "error": (proc.stderr or proc.stdout or "").strip()[:500] or f"exit {proc.returncode}",
                }
            stdout = (proc.stdout or "").strip()
            # Try to parse as JSON
            if stdout.startswith("{") or stdout.startswith("["):
                try:
                    return {"ok": True, "result": json.loads(stdout)}
                except json.JSONDecodeError:
                    pass
            return {"ok": True, "result": stdout}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"timeout after {timeout:.1f}s"}
        except FileNotFoundError:
            return {"ok": False, "error": f"command not found: {args[0]}"}
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def _shell(self, cmd: str, timeout: float = 10.0) -> Dict[str, Any]:
        """Run a shell command. Returns stdout or stderr."""
        try:
            proc = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=timeout,
            )
            out = (proc.stdout or "").strip()
            err = (proc.stderr or "").strip()
            if proc.returncode != 0:
                return {"ok": False, "error": err[:500] or out[:500] or f"exit {proc.returncode}"}
            return {"ok": True, "result": out}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"timeout after {timeout:.1f}s"}
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    # ----------------- public subcommands -----------------
    def battery(self) -> Dict[str, Any]:
        return self._run("termux-battery-status")

    def wifi(self) -> Dict[str, Any]:
        return self._run("termux-wifi-connectioninfo")

    def location(self, timeout: float = 15.0) -> Dict[str, Any]:
        # termux-location needs a provider + a wait time
        return self._run("termux-location", "-p", "gps", "-r", "once",
                         timeout=timeout)

    def notify(self, args: List[str]) -> Dict[str, Any]:
        msg = " ".join(args) if args else "(empty)"
        return self._run("termux-notification",
                         "--title", "Orca", "--content", msg)

    def vibrate(self, args: List[str]) -> Dict[str, Any]:
        ms = args[0] if args else "300"
        return self._run("termux-vibrate", "-d", str(ms), "-f")

    def toast(self, args: List[str]) -> Dict[str, Any]:
        msg = " ".join(args) if args else "(empty)"
        return self._run("termux-toast", msg)

    def clipboard(self) -> Dict[str, Any]:
        return self._run("termux-clipboard-get")

    def speak(self, args: List[str]) -> Dict[str, Any]:
        text = " ".join(args) if args else "(empty)"
        return self._run("termux-tts-speak", text)

    def torch(self, args: List[str]) -> Dict[str, Any]:
        state = (args[0] if args else "on").lower()
        if state not in ("on", "off"):
            return {"ok": False, "error": "torch: state must be 'on' or 'off'"}
        return self._run("termux-torch", state)

    def share(self, args: List[str]) -> Dict[str, Any]:
        text = " ".join(args) if args else ""
        if not text:
            return {"ok": False, "error": "share: missing text"}
        # termux-share takes the text as positional args, last arg is the action
        return self._run("termux-share", "-a", "android.intent.action.SEND",
                         "--es", "android.intent.extra.TEXT", text)

    def uptime(self) -> Dict[str, Any]:
        return self._shell("uptime -p 2>/dev/null || uptime")

    def storage(self) -> Dict[str, Any]:
        return self._shell("df -h $HOME 2>/dev/null | tail -n 1")

    def wake(self) -> Dict[str, Any]:
        return self._run("termux-wake-lock")

    def ping(self) -> Dict[str, Any]:
        return {"ok": True, "result": "pong"}

    def run(self, args: List[str]) -> Dict[str, Any]:
        if not args:
            return {"ok": False, "error": "run: missing command"}
        return self._shell(" ".join(args), timeout=30.0)

    # ----------------- dispatcher -----------------
    def execute(self, subcommand: str, args: List[str]) -> Dict[str, Any]:
        method = getattr(self, subcommand, None)
        if not callable(method):
            return {
                "ok": False,
                "error": f"unknown subcommand: {subcommand!r}",
                "hint": f"allowed: {ALLOWED_DEFAULT}",
            }
        try:
            return method(args) if subcommand in (
                "notify", "vibrate", "toast", "speak", "torch", "share", "run"
            ) else method()
        except Exception as exc:
            return {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc()[:500],
            }


# ---------------------------------------------------------------------
# Bridge daemon
# ---------------------------------------------------------------------
class Bridge:
    """The polling daemon. State: server URL, token, last-seen time."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.url = config["server_url"].rstrip("/")
        self.token = config["auth_token"]
        self.device_name = config.get("device_name", "termux-device")
        self.poll = float(config.get("poll_interval", DEFAULT_POLL))
        self.event_interval = float(config.get("event_interval", DEFAULT_EVENT))
        self.allowed = set(config.get("allowed_commands", ALLOWED_DEFAULT))
        self.api = TermuxAPI()
        self.last_seen = 0.0
        self.last_event = 0.0
        self.running = True
        self.errors_in_a_row = 0

    def stop(self) -> None:
        self.running = False

    def _post_result(self, cmd_id: str, ok: bool, result: Any, error: str = "") -> bool:
        try:
            _http_json(
                f"{self.url}/result",
                method="POST",
                body={"id": cmd_id, "ok": ok, "result": result, "error": error},
                token=self.token,
                timeout=10.0,
            )
            return True
        except Exception as exc:
            _log(f"failed to post result for {cmd_id}: {exc}", "WARN")
            return False

    def _post_event(self, kind: str, data: Dict[str, Any]) -> bool:
        try:
            _http_json(
                f"{self.url}/event",
                method="POST",
                body={"kind": kind, "data": data},
                token=self.token,
                timeout=10.0,
            )
            return True
        except Exception as exc:
            _log(f"failed to post event {kind}: {exc}", "WARN")
            return False

    def _handle_command(self, cmd: Dict[str, Any]) -> None:
        sub = cmd.get("subcommand", "")
        args = cmd.get("args", [])
        if sub not in self.allowed:
            self._post_result(
                cmd["id"], ok=False,
                error=f"subcommand {sub!r} not in allow-list",
            )
            _log(f"rejected command: {sub!r} (not in allow-list)", "WARN")
            return
        _log(f"execute: {sub} {args}")
        result = self.api.execute(sub, args)
        self._post_result(
            cmd["id"],
            ok=result.get("ok", False),
            result=result.get("result"),
            error=result.get("error", ""),
        )

    def _emit_health_event(self) -> None:
        """Push a battery + storage snapshot to the bot."""
        try:
            battery = self.api.battery()
            storage = self.api.storage()
            self._post_event("health", {
                "device": self.device_name,
                "battery": battery.get("result") if battery.get("ok") else None,
                "storage": storage.get("result") if storage.get("ok") else None,
                "ts": time.time(),
            })
        except Exception as exc:
            _log(f"health event failed: {exc}", "WARN")

    def run(self) -> None:
        """Main loop. Returns when stop() is called."""
        _log(f"starting: server={self.url} device={self.device_name} "
             f"poll={self.poll}s event={self.event_interval}s")
        _log(f"allowed: {sorted(self.allowed)}")
        _log(f"termux-api installed: {self.api.has_termux_api}")
        # Initial health event
        self._emit_health_event()
        while self.running:
            try:
                pending = _http_json(
                    f"{self.url}/pending?since={self.last_seen}",
                    token=self.token,
                    timeout=10.0,
                )
                cmds = pending.get("commands", [])
                for cmd in cmds:
                    self._handle_command(cmd)
                self.errors_in_a_row = 0
                if cmds:
                    _log(f"processed {len(cmds)} command(s)")
            except urllib.error.HTTPError as e:
                self.errors_in_a_row += 1
                _log(f"http error: {e.code} {e.reason}", "WARN")
            except urllib.error.URLError as e:
                self.errors_in_a_row += 1
                _log(f"network error: {e.reason}", "WARN")
            except Exception as exc:
                self.errors_in_a_row += 1
                _log(f"unexpected error: {type(exc).__name__}: {exc}", "ERROR")
                _log(traceback.format_exc(), "ERROR")
            # Periodic health event
            now = time.time()
            if now - self.last_event > self.event_interval:
                self.last_event = now
                self._emit_health_event()
            # Backoff if we're flapping
            sleep_for = self.poll
            if self.errors_in_a_row >= 3:
                sleep_for = min(30.0, self.poll * (2 ** min(5, self.errors_in_a_row - 2)))
                _log(f"backing off: sleeping {sleep_for:.1f}s ({self.errors_in_a_row} errors in a row)", "WARN")
            time.sleep(sleep_for)
        _log("stopped")


# ---------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------
def _load_config() -> Dict[str, Any]:
    """Load termux_bridge.json. If missing, create a template and exit."""
    if not CONFIG_PATH.exists():
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        template = {
            "server_url": os.environ.get("ORCA_BRIDGE_URL", "http://YOUR-ORCA-HOST:8765"),
            "auth_token": os.environ.get("ORCA_BRIDGE_TOKEN", "paste-token-from-TERMUX_BRIDGE_TOKEN"),
            "device_name": os.environ.get("ORCA_DEVICE_NAME", "my-phone"),
            "poll_interval": DEFAULT_POLL,
            "event_interval": DEFAULT_EVENT,
            "allowed_commands": ALLOWED_DEFAULT,
        }
        CONFIG_PATH.write_text(json.dumps(template, indent=2, ensure_ascii=False),
                                encoding="utf-8")
        print(f"[!] Created template config at {CONFIG_PATH}")
        print(f"    Edit it with your Orca server URL and token, then re-run.")
        sys.exit(1)
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[!] Config at {CONFIG_PATH} is not valid JSON: {exc}")
        sys.exit(2)


# ---------------------------------------------------------------------
# CLI helpers (handy for testing in Termux)
# ---------------------------------------------------------------------
def cli_execute() -> int:
    """Run a single subcommand locally, print result. Useful for testing
    termux-api in Termux without going through the bridge:

        python termux_bridge.py exec battery
        python termux_bridge.py exec notify "hello from orca"
    """
    if len(sys.argv) < 3 or sys.argv[1] != "exec":
        print("usage: termux_bridge.py exec <subcommand> [args...]", file=sys.stderr)
        return 2
    api = TermuxAPI()
    sub = sys.argv[2]
    args = sys.argv[3:]
    out = api.execute(sub, args)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("ok") else 1


def cli_doctor() -> int:
    """Check that termux-api is installed and the bin paths work."""
    print("Orca Termux Bridge doctor")
    print(f"  Python:    {sys.version.split()[0]}")
    print(f"  Platform:  {sys.platform}")
    print(f"  Log dir:   {LOG_DIR}")
    print(f"  Config:    {CONFIG_PATH}")
    cmds = [
        "termux-battery-status", "termux-wifi-connectioninfo",
        "termux-location", "termux-notification", "termux-toast",
        "termux-vibrate", "termux-torch", "termux-share",
        "termux-clipboard-get", "termux-tts-speak", "termux-wake-lock",
        "termux-call-log", "termux-sms-list", "termux-camera-photo",
    ]
    found = 0
    for c in cmds:
        ok = shutil.which(c) is not None
        print(f"  {'[OK]' if ok else '[--]'} {c}")
        if ok:
            found += 1
    print(f"\n  Found {found}/{len(cmds)} termux-api helpers")
    if found == 0:
        print("  [!] Install with: pkg install termux-api")
        print("      Then install the Termux:API app from F-Droid")
    return 0 if found else 1


# ---------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------
def main() -> int:
    if len(sys.argv) > 1:
        if sys.argv[1] == "exec":
            return cli_execute()
        if sys.argv[1] == "doctor":
            return cli_doctor()
        if sys.argv[1] in ("-h", "--help", "help"):
            print(__doc__)
            return 0
    config = _load_config()
    bridge = Bridge(config)
    try:
        bridge.run()
    except KeyboardInterrupt:
        _log("interrupted")
        bridge.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
