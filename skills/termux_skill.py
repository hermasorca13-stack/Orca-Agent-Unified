"""
skills/termux_skill.py - Telegram command surface for the Orca<->Termux bridge.

The bot calls `cmd_termux(update, context)` from `telegram_bot/bot.py`.
This skill:

  1. Parses the subcommand and args from the user message
  2. Validates against the allow-list (defence in depth - the phone
     also enforces this, but we want to reject early)
  3. Calls `tools/termux_server.push_command(chat_id, sub, args)`
     which blocks (with polling) until the phone answers
  4. Formats the result for Telegram (Markdown, 4096-char cap)

The user sees:

    /termux battery
    -> Phone answered in 1.2s
       Battery: 87%  Status: discharging  Temp: 28.4°C

If the phone is offline:

    /termux battery
    -> Phone didn't answer in 15.0s. Is the bridge running?
       Run on phone: nohup python termux_bridge.py &

Subcommand reference (also exposed via /help):

    /termux battery              -> battery status (JSON)
    /termux wifi                 -> SSID, IP, link speed
    /termux location             -> GPS lat/lon
    /termux notify <message>     -> show a phone notification
    /termux toast <message>      -> short toast popup
    /termux vibrate [ms]         -> vibrate (default 300ms)
    /termux speak <text>         -> TTS via Android
    /termux torch [on|off]       -> toggle flashlight
    /termux share <text>         -> open share sheet
    /termux clipboard            -> get clipboard text
    /termux uptime               -> phone uptime
    /termux storage              -> df -h ~
    /termux wake                 -> wake + hold screen
    /termux run <shell command>  -> run any shell command
    /termux ping                 -> health check
    /termux status               -> bridge server stats
    /termux setup                -> show config + connection token
    /termux help                 -> this help text
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

# Lazy import of the server (heavy: pulls in FastAPI)
_server = None
_server_load_failed = False


def _get_server():
    """Lazy-import tools.termux_server so the bot doesn't load
    FastAPI at import time (saves ~80ms on cold start)."""
    global _server, _server_load_failed
    if _server is not None:
        return _server
    if _server_load_failed:
        return None
    try:
        # tools/ is at the project root, sibling of skills/
        from tools import termux_server  # type: ignore
        _server = termux_server
        return _server
    except Exception as exc:
        _server_load_failed = True
        logger.warning("termux_skill: failed to import termux_server: {}", exc)
        return None


# ---------------------------------------------------------------------
# Subcommand catalogue (single source of truth, mirrored on the phone)
# ---------------------------------------------------------------------
SUBCOMMANDS: Dict[str, Dict[str, Any]] = {
    "battery":   {"args": 0, "timeout": 5.0,
                  "summary": "Battery status (%, health, temp)"},
    "wifi":      {"args": 0, "timeout": 5.0,
                  "summary": "Wi-Fi connection info (SSID, IP, link speed)"},
    "location":  {"args": 0, "timeout": 20.0,
                  "summary": "GPS location (lat/lon/accuracy)"},
    "notify":    {"args": "*", "timeout": 5.0,
                  "summary": "Show a phone notification: /termux notify <msg>"},
    "toast":     {"args": "*", "timeout": 5.0,
                  "summary": "Show a short toast: /termux toast <msg>"},
    "vibrate":   {"args": "?", "timeout": 5.0,
                  "summary": "Vibrate N ms: /termux vibrate 500"},
    "speak":     {"args": "*", "timeout": 8.0,
                  "summary": "Text-to-speech: /termux speak hello"},
    "torch":     {"args": "?", "timeout": 5.0,
                  "summary": "Toggle flashlight: /termux torch on|off"},
    "share":     {"args": "*", "timeout": 5.0,
                  "summary": "Open share sheet: /termux share <text>"},
    "clipboard": {"args": 0, "timeout": 5.0,
                  "summary": "Get clipboard text"},
    "uptime":    {"args": 0, "timeout": 5.0,
                  "summary": "Phone uptime"},
    "storage":   {"args": 0, "timeout": 5.0,
                  "summary": "Storage info (df -h)"},
    "wake":      {"args": 0, "timeout": 5.0,
                  "summary": "Wake + hold screen"},
    "ping":      {"args": 0, "timeout": 5.0,
                  "summary": "Health check"},
    "run":       {"args": "*", "timeout": 30.0,
                  "summary": "Run a shell command: /termux run ls -la"},
    "status":    {"args": 0, "timeout": 5.0,
                  "summary": "Bridge server stats (no phone needed)"},
    "setup":     {"args": 0, "timeout": 5.0,
                  "summary": "Show config + auth token (no phone needed)"},
    "help":      {"args": 0, "timeout": 5.0,
                  "summary": "Show this help"},
}


# Synonyms: Arabic / Egyptian words that map to an English subcommand.
# The NL intent_skill often extracts the raw Arabic word; this map
# lets the bot translate it before dispatching to the phone.
SUBCOMMAND_SYNONYMS: Dict[str, str] = {
    # battery
    "بطارية": "battery", "البطارية": "battery", "بطاريه": "battery",
    "البطاريه": "battery", "شحن": "battery", "الشحن": "battery",
    # wifi
    "واي_فاي": "wifi", "الواي_فاي": "wifi", "wifi": "wifi",
    "wifi": "wifi", "الانترنت": "wifi", "نت": "wifi",
    # location
    "موقع": "location", "الموقع": "location", "مكان": "location",
    "المكان": "location", "جي_بي_اس": "location", "gps": "location",
    # notify
    "اشعار": "notify", "إشعار": "notify", "تنبيه": "notify",
    "notification": "notify",
    # vibrate
    "اهتزاز": "vibrate", "اهتز": "vibrate",
    # torch
    "كشاف": "torch", "الكشاف": "torch", "فلاش": "torch", "الفلاش": "torch",
    "torch": "torch", "النور": "torch",
    # clipboard
    "حافظه": "clipboard", "حافظة": "clipboard", "نسخ": "clipboard",
    "clipboard": "clipboard",
    # uptime
    "مدة_التشغيل": "uptime", "uptime": "uptime",
    # storage
    "تخزين": "storage", "مساحه": "storage", "مساحة": "storage",
    "storage": "storage",
    # wake
    "صحى": "wake", "wake": "wake",
    # ping
    "تست": "ping", "اختبار": "ping", "ping": "ping",
    # run
    "شغل": "run", "نفذ": "run", "اعمل": "run", "run": "run",
    # status
    "حالة": "status", "حاله": "status", "status": "status",
}


# ---------------------------------------------------------------------
# Public entry point: cmd_termux(update, context)
# ---------------------------------------------------------------------
def cmd_termux(args: List[str], chat_id: int) -> str:
    """The /termux command handler.

    Args:
        args: tokens after `/termux` (e.g. ["battery"] or
              ["notify", "Hello", "from", "Orca"])
        chat_id: the originating Telegram chat id (so the result
                 can be matched back to the right user).

    Returns:
        A Markdown-formatted string for Telegram. Never raises -
        all errors are caught and turned into user-friendly messages.
    """
    if not args:
        return _help_text()
    sub = args[0].lower().strip()
    # Translate Arabic / Egyptian synonyms to English subcommand names
    sub = SUBCOMMAND_SYNONYMS.get(sub, sub)
    rest = args[1:]

    if sub not in SUBCOMMANDS:
        return f"Unknown subcommand: `{sub}`\n\n{_help_text()}"

    # Local-only subcommands (no phone round-trip)
    if sub == "help":
        return _help_text()
    if sub == "setup":
        return _setup_text()
    if sub == "status":
        return _status_text()

    # Validate args
    spec = SUBCOMMANDS[sub]
    arg_spec = spec["args"]
    if arg_spec == 0 and rest:
        return f"`/termux {sub}` takes no arguments. Try `/termux help`."
    if isinstance(arg_spec, int) and arg_spec > 0 and len(rest) < arg_spec:
        return f"`/termux {sub}` needs at least {arg_spec} argument(s)."
    # Subcommands that REQUIRE at least one argument (not just any number)
    if sub in ("run", "notify", "toast", "speak", "share") and not rest:
        return f"`/termux {sub}` needs at least 1 argument."

    server = _get_server()
    if server is None:
        return (
            "❌ Termux bridge server failed to load. "
            "Make sure `tools/termux_server.py` is in the repo and "
            "FastAPI is installed (`pip install fastapi uvicorn`)."
        )

    timeout = float(spec.get("timeout", 10.0))
    t0 = time.monotonic()
    try:
        result = server.push_command(
            chat_id=chat_id,
            subcommand=sub,
            args=rest,
            timeout=timeout,
        )
    except Exception as exc:
        logger.exception("termux_skill: push_command failed")
        return f"❌ Bridge error: `{type(exc).__name__}: {exc}`"

    elapsed_ms = (time.monotonic() - t0) * 1000
    if not result.get("ok") and result.get("status") == "pending":
        return (
            f"⏳ Phone didn't answer in {timeout:.1f}s. "
            f"Is the bridge running?\n\n"
            f"On phone, run:\n"
            f"```\n"
            f"pkg install python termux-api\n"
            f"mkdir -p ~/orca_bridge\n"
            f"cd ~/orca_bridge\n"
            f"# copy termux_bridge.py + termux_bridge.json\n"
            f"python termux_bridge.py doctor\n"
            f"nohup python termux_bridge.py &\n"
            f"```\n"
            f"Bridge server: `{server.get_endpoint_url()}`"
        )
    if not result.get("ok"):
        return _format_error(sub, result)
    return _format_success(sub, result, elapsed_ms)


# ---------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------
TELEGRAM_MAX = 3800  # leave room for headers + Markdown

def _truncate(text: str, limit: int = TELEGRAM_MAX) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 50] + "\n\n[... truncated ...]"


def _format_success(sub: str, result: Dict[str, Any], elapsed_ms: float) -> str:
    payload = result.get("result")
    if isinstance(payload, (dict, list)):
        # Try to render as a nice code block
        body = json.dumps(payload, ensure_ascii=False, indent=2)
        return (
            f"📱 `{sub}` answered in {elapsed_ms / 1000:.2f}s\n"
            f"```json\n{_truncate(body)}\n```"
        )
    if isinstance(payload, str):
        return f"📱 `{sub}` answered in {elapsed_ms / 1000:.2f}s\n```\n{_truncate(payload)}\n```"
    return f"📱 `{sub}` answered in {elapsed_ms / 1000:.2f}s\n```\n{_truncate(str(payload))}\n```"


def _format_error(sub: str, result: Dict[str, Any]) -> str:
    err = result.get("error") or "unknown error"
    hint = ""
    if "termux-api" in err.lower() or "not found" in err.lower():
        hint = "\n\n💡 On the phone, install: `pkg install termux-api`"
    elif "network" in err.lower() or "connection" in err.lower():
        hint = "\n\n💡 Check phone's internet connection"
    elif "permission" in err.lower():
        hint = "\n\n💡 Grant the Termux:API app the required permission in Android settings"
    return f"❌ `{sub}` failed: `{err}`{hint}"


def _status_text() -> str:
    """Show server stats. Works even when the phone is offline."""
    server = _get_server()
    if server is None:
        return "❌ Bridge server not loaded."
    try:
        s = server._queue.stats()
        token = server.get_token()
        url = server.get_endpoint_url()
    except Exception as exc:
        return f"❌ Bridge error: `{exc}`"
    return (
        "📊 *Orca ↔ Termux Bridge Status*\n\n"
        f"Server:     `{url}`\n"
        f"Queue size: `{s.get('queue_size', 0)}` pending\n"
        f"Completed:  `{s.get('completed_total', 0)}` total\n"
        f"Last poll:  `{s.get('last_poll', 0):.0f}` (epoch)\n"
        f"Token:      `{token[:4]}...{token[-4:]}`\n"
    )


def _setup_text() -> str:
    """Show the user the config they need to put on the phone."""
    server = _get_server()
    if server is None:
        return "❌ Bridge server not loaded."
    token = server.get_token()
    url = server.get_endpoint_url()
    return (
        "🛠 *Orca ↔ Termux Bridge - Phone Setup*\n\n"
        f"On your phone (Termux), run:\n"
        f"```\n"
        f"pkg install python termux-api\n"
        f"mkdir -p ~/orca_bridge\n"
        f"cd ~/orca_bridge\n"
        f"# Download the daemon:\n"
        f"curl -O https://raw.githubusercontent.com/hermasorca13-stack/\n"
        f"     Orca-Agent-Unified/master/tools/termux_bridge.py\n"
        f"# Create the config:\n"
        f"cat > termux_bridge.json <<'JSON'\n"
        + json.dumps({
            "server_url": url,
            "auth_token": token,
            "device_name": "my-phone",
            "poll_interval": 3.0,
            "event_interval": 300.0,
            "allowed_commands": sorted([
                "battery", "wifi", "location", "run", "notify",
                "vibrate", "toast", "clipboard", "speak", "torch",
                "share", "uptime", "storage", "wake", "ping",
            ]),
        }, indent=2) + "\n"
        f"JSON\n"
        f"# Sanity check:\n"
        f"python termux_bridge.py doctor\n"
        f"# Start the daemon (detached):\n"
        f"nohup python termux_bridge.py >/dev/null 2>&1 &\n"
        f"```\n\n"
        f"Then come back here and try:\n"
        f"  /termux ping\n"
        f"  /termux battery\n"
    )


def _help_text() -> str:
    lines = ["📱 *Orca ↔ Termux Bridge - Subcommands*\n"]
    for sub, spec in SUBCOMMANDS.items():
        lines.append(f"  `/termux {sub:<10}` - {spec['summary']}")
    lines.append(
        "\nLocal-only: `setup`, `status`, `help` (no phone needed)\n"
        "The phone must be running `termux_bridge.py` for the rest."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------
# Skill-card for /skills list
# ---------------------------------------------------------------------
def skill_card() -> Dict[str, Any]:
    """Compact representation for SKILL_CATALOG."""
    return {
        "name": "termux",
        "title": "Termux Bridge",
        "summary": "Bidirectional bridge to a phone running Termux",
        "commands": [f"/termux {sub}" for sub in SUBCOMMANDS],
        "requires": ["TERMUX_BRIDGE_TOKEN"],
        "version": "1.0.0",
    }
