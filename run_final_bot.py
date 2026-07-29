#!/usr/bin/env python3
"""
run_final_bot.py — Minimal legacy wrapper.

WARNING: This file is DEPRECATED. Use `python orca.py bot` instead.
Kept only to avoid breaking older deployment scripts.

It now does exactly what orca.py does, no duplicate getUpdates poller.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Hand off — no second bot instance
if __name__ == "__main__":
    os.execvp(sys.executable, [sys.executable, str(ROOT / "orca.py"), "bot"])
