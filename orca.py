# orca.py - Orca Agent main entrypoint (unified)
"""
One file, one entrypoint. Modes:
  python orca.py bot       # start Telegram bot (long-polling)
  python orca.py sync      # push to GitHub
  python orca.py status    # print system status
  python orca.py doctor    # engineering checks (duplicates, imports, structure)
  python orca.py tokens    # list API tokens
"""
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

def boot():
    """Common startup: load config, skills, verify telegram & github."""
    setup_logging()
    logger.info("=" * 60)
    logger.info("ORCA AGENT — START")
    logger.info("=" * 60)
    config.validate()
    from skills.orca_skills import load_all
    loaded = load_all()
    logger.info(f"Skills loaded: {len(loaded)}")
    # Try to bring the OrcaAgent (LLM + memory + 25+ skills) online (non-fatal if no LLM key)
    try:
        from core.agent_loader import bridge
        if bridge.initialize():
            logger.info(f"Agent skills registered: {len(bridge.list_skills())}")
        else:
            logger.info(f"Agent bridge idle: {bridge.reason}")
    except Exception as e:
        logger.warning(f"Agent bridge boot skipped: {e}")
    return loaded

def verify_telegram() -> bool:
    import urllib.request, json
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{config.TG_TOKEN}/getMe", timeout=10) as r:
            d = json.loads(r.read())
            if d.get("ok"):
                logger.info(f"✅ Telegram OK: @{d['result']['username']}")
                return True
    except Exception as e:
        logger.error(f"Telegram verify failed: {e}")
    return False

def verify_github() -> bool:
    import urllib.request
    if not config.GH_TOKEN:
        logger.warning("GITHUB_TOKEN not set — sync will use local git fallback")
        return False
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{config.GH_USER}/{config.GH_REPO}",
            headers={
                "Authorization": f"token {config.GH_TOKEN}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "OrcaAgent/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            logger.info(f"✅ GitHub OK: {config.GH_REPO}")
            return True
    except Exception as e:
        logger.warning(f"GitHub verify: {e}")
        return False

def cmd_bot(_):
    from telegram_bot.bot import OrcaBot
    OrcaBot().run()

def cmd_sync(_):
    from github_sync.gh_sync import sync_to_github
    r = sync_to_github()
    print(r)
    return r

def cmd_status(_):
    from skills.orca_skills import names
    from api_manager.api_manager import api
    print(f"Bot: @{config.TG_USERNAME}")
    print(f"User: {config.GH_USER}")
    print(f"Repo: {config.GH_REPO}@{config.GH_BRANCH}")
    print(f"GH token: {'yes' if config.GH_TOKEN else 'no'}")
    print(f"Master token: {'yes' if config.ORCA_MASTER else 'no'}")
    print(f"Skills: {names()}")
    print(f"Tokens: {api.count()}")

def cmd_tokens(_):
    from api_manager.api_manager import api
    for t in api.list_tokens():
        print(t)

def cmd_doctor(_):
    """Engineering checks: duplicates, structure, import health, agent bridge."""
    print("=== ORCA DOCTOR ===")
    print(f"Workspace: {config.ROOT}")
    # Check for duplicate filenames across packages
    seen = {}
    dups = []
    for p in config.ROOT.rglob("*.py"):
        if "__pycache__" in str(p) or ".git" in str(p):
            continue
        name = p.name
        seen.setdefault(name, []).append(str(p.relative_to(config.ROOT)))
    for n, locs in seen.items():
        if len(locs) > 1 and n not in {"__init__.py"}:
            dups.append((n, locs))
    if dups:
        print("⚠️  Duplicate filenames detected (functional ones are intentional wrappers):")
        for n, locs in dups:
            print(f"   {n}: {locs}")
    else:
        print("✅ No duplicate filenames")
    # Check __init__.py presence
    pkgs = ["core", "api_manager", "telegram_bot", "github_sync", "android_bridge", "skills", "src", "platforms"]
    for pkg in pkgs:
        init = config.ROOT / pkg / "__init__.py"
        if not init.exists() and pkg in {"core", "api_manager", "telegram_bot", "github_sync", "android_bridge", "skills"}:
            print(f"❌ {pkg}/__init__.py MISSING")
        else:
            print(f"{'✅' if init.exists() else '— '} {pkg}/__init__.py")
    # Import health: try importing each package
    for pkg in ["core", "api_manager", "telegram_bot", "github_sync", "android_bridge", "skills"]:
        try:
            __import__(pkg)
            print(f"✅ import {pkg}")
        except Exception as e:
            print(f"❌ import {pkg}: {e}")
    # Agent bridge diagnostic
    try:
        from core.agent_loader import bridge
        bridge.initialize()
        print(f"{'🟢' if bridge.ready else '🔴'} AgentBridge ready={bridge.ready} skills={len(bridge.list_skills())} reason={bridge.reason}")
    except Exception as e:
        print(f"❌ AgentBridge: {e}")
    # Memory diagnostic
    try:
        from core.memory_instance import get_memory
        mem = get_memory()
        stats = mem.get_stats() if hasattr(mem, "get_stats") else {}
        print(f"✅ MemorySystem db={getattr(mem, 'db_path', '?')} stats={stats}")
    except Exception as e:
        print(f"❌ MemorySystem: {e}")
    # File size sanity
    heavy = []
    for p in config.ROOT.rglob("*.py"):
        if "__pycache__" in str(p): continue
        size = p.stat().st_size
        if size > 50_000:
            heavy.append((p.relative_to(config.ROOT), size))
    if heavy:
        print(f"⚠️  Large files (>50KB): {heavy}")
    else:
        print("✅ No oversized files")
    print("=== DOCTOR OK ===")

def main():
    boot()
    verify_telegram()
    verify_github()

    parser = argparse.ArgumentParser(description="Orca Agent CLI")
    sub = parser.add_subparsers(dest="mode")
    sub.add_parser("bot", help="start Telegram bot")
    sub.add_parser("sync", help="push to GitHub")
    sub.add_parser("status", help="print status")
    sub.add_parser("tokens", help="list API tokens")
    sub.add_parser("doctor", help="engineering checks")
    args = parser.parse_args()

    mode = args.mode or "status"
    fn = {
        "bot": cmd_bot,
        "sync": cmd_sync,
        "status": cmd_status,
        "tokens": cmd_tokens,
        "doctor": cmd_doctor,
    }.get(mode)
    if fn:
        fn(args)
    else:
        print("Usage: python orca.py {bot|sync|status|tokens|doctor}")

if __name__ == "__main__":
    main()
