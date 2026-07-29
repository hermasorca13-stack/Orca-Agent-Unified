#!/usr/bin/env python3
"""
start_agent.py — Production wrapper that delegates to orca.py
This is kept for backward-compat with deployment scripts that call `python start_agent.py`.
Internally it just runs `python -m orca bot` so there is only ONE entrypoint that
actually owns the Telegram long-polling loop.
"""
import os
import sys
from pathlib import Path

# Force project root onto sys.path (works from any CWD)
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Single-instance guard — kill any other getUpdates pollers (e.g. run_final_bot.py)
# Telegram API: only ONE process may own a bot at a time.
import urllib.request, json, time

def _kill_conflicts():
    try:
        with open(ROOT / ".env") as f:
            env = dict(line.strip().split("=", 1) for line in f if "=" in line and not line.startswith("#"))
        token = env.get("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            return
        # We can't actually kill remote processes, but we delete any webhook and
        # wait for the API to release the slot. This avoids the
        # "Conflict: terminated by other getUpdates request" race.
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=true",
            timeout=5,
        ) as r:
            json.loads(r.read())
    except Exception:
        pass
    time.sleep(1)

_kill_conflicts()

# Delegate to the canonical entrypoint
if __name__ == "__main__":
    os.execvp(sys.executable, [sys.executable, str(ROOT / "orca.py"), "bot"])
