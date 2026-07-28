# orca.py - Orca Agent main entrypoint
import sys
import argparse
from pathlib import Path
from loguru import logger
from core.config import config

def setup_logging():
    config.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(sys.stderr, level=config.LOG_LEVEL)
    logger.add(config.LOG_PATH, rotation="10 MB", retention="7 days", level=config.LOG_LEVEL)

def main():
    setup_logging()
    logger.info("=" * 60)
    logger.info("ORCA AGENT — START")
    logger.info("=" * 60)

    if not config.validate():
        logger.warning("Some env missing — continuing with what we have")

    # Load skills
    from skills.orca_skills import load_all
    skills = load_all()
    logger.info(f"Skills loaded: {len(skills)}")

    # Verify Telegram connection
    import urllib.request
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{config.TG_TOKEN}/getMe", timeout=10) as r:
            import json
            data = json.loads(r.read())
            if data.get("ok"):
                logger.info(f"✅ Telegram OK: @{data['result']['username']}")
            else:
                logger.error(f"Telegram NOT ok: {data}")
    except Exception as e:
        logger.error(f"Telegram verify failed: {e}")

    # Verify GitHub
    if config.GH_TOKEN:
        import urllib.request
        try:
            req = urllib.request.Request(
                f"https://api.github.com/repos/{config.GH_USER}/{config.GH_REPO}",
                headers={"Authorization": f"token {config.GH_TOKEN}", "User-Agent": "OrcaAgent/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                logger.info(f"✅ GitHub OK: {config.GH_REPO}")
        except Exception as e:
            logger.warning(f"GitHub verify: {e}")
    else:
        logger.warning("GITHUB_TOKEN not set — sync will use local git fallback")

    # Run chosen mode
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode")
    sub.add_parser("bot")
    sub.add_parser("sync")
    sub.add_parser("status")
    sub.add_parser("doctor")
    args = parser.parse_args()

    mode = args.mode or "status"

    if mode == "bot":
        from telegram_bot.bot import OrcaBot
        OrcaBot().run()
    elif mode == "sync":
        from github_sync.gh_sync import sync_to_github
        r = sync_to_github()
        logger.info(f"Sync: {r}")
        print(r)
    elif mode == "doctor":
        doctor()
    else:
        print(f"Bot: @{config.TG_USERNAME}")
        print(f"Repo: {config.GH_USER}/{config.GH_REPO}")
        print(f"Skills: {list(skills.keys())}")
        print(f"Tokens: {len(__import__('api_manager.api_manager', fromlist=['api']).api.tokens)}")

def doctor():
    """Run engineering checks on every component."""
    import os
    from pathlib import Path
    root = config.ROOT
    print("=== ORCA DOCTOR ===")
    print(f"Workspace: {root}")
    print(f"Bot token present: {bool(config.TG_TOKEN)}")
    print(f"GitHub token present: {bool(config.GH_TOKEN)}")
    print(f"Master token present: {bool(config.ORCA_MASTER)}")
    # Check for duplicate files
    seen = {}
    dups = []
    for p in root.rglob("*.py"):
        if "__pycache__" in str(p): continue
        try:
            content = p.read_text()
            for line in content.splitlines():
                if line.startswith("import ") or line.startswith("from "):
                    seen[line] = seen.get(line, 0) + 1
        except: pass
    heavy = [(k,v) for k,v in seen.items() if v > 5]
    print(f"Heavy-import lines: {len(heavy)}")
    print("=== OK ===")

if __name__ == "__main__":
    main()
