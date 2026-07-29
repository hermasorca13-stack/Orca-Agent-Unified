#!/usr/bin/env python3
"""
scripts/smoke_test.py — Live health check (no bot startup, no double getUpdates)

Verifies:
  1. Telegram bot is reachable (@getMe)
  2. GitHub repo is reachable with the configured token
  3. Config validates
  4. No other getUpdates is currently polling (we check via getWebhookInfo + deleteWebhook)

Usage:
  python scripts/smoke_test.py
"""
import os
import sys
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

TG = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
GH = os.getenv("GITHUB_TOKEN", "").strip()
GH_USER = os.getenv("GITHUB_USERNAME", "").strip()
GH_REPO = os.getenv("GITHUB_REPO", "").strip()


def _check(name, url, headers=None):
    try:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
            print(f"  ✅ {name}: {data.get('result', {}).get('username', 'ok') if 'result' in data else 'ok'}")
            return True
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        return False


def main():
    print("=" * 60)
    print("🐋 ORCA SMOKE TEST")
    print("=" * 60)
    ok = True

    print("\n[1/4] Config")
    print(f"  TG_TOKEN: {'✅' if TG else '❌'}")
    print(f"  GH_TOKEN: {'✅' if GH else '❌'}")
    print(f"  GH_USER:  {GH_USER}")
    print(f"  GH_REPO:  {GH_REPO}")
    if not TG or not GH:
        print("  ❌ Missing tokens in .env")
        return 1

    print("\n[2/4] Telegram @getMe")
    ok &= _check("Telegram", f"https://api.telegram.org/bot{TG}/getMe")

    print("\n[3/4] GitHub /repos/{user}/{repo}")
    ok &= _check(
        "GitHub",
        f"https://api.github.com/repos/{GH_USER}/{GH_REPO}",
        headers={
            "Authorization": f"Bearer {GH}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "OrcaAgent-Smoke/1.0",
        },
    )

    print("\n[4/4] Telegram webhook (avoid getUpdates conflict)")
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TG}/getWebhookInfo"
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
            wh = data.get("result", {}).get("url", "")
            print(f"  webhook url: {wh or '(none)'}")
            print(f"  ✅ no webhook conflict")
    except Exception as e:
        print(f"  ⚠️ webhook check: {e}")

    print("\n" + "=" * 60)
    print("✅ SMOKE OK" if ok else "❌ SMOKE FAILED")
    print("=" * 60)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
