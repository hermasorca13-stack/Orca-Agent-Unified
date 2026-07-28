# 🐋 Orca Agent — Unified Production

Real, working agent: **Telegram + GitHub + Android bridge + Universal API** in one clean Python package. No duplicates, no Node.js leftovers, single source of truth.

## Structure
```
orca-agent/
├── orca.py                     # entrypoint (bot|sync|status|tokens|doctor)
├── requirements.txt
├── .env / .env.example
├── core/
│   ├── __init__.py
│   └── config.py               # single env loader
├── api_manager/
│   ├── __init__.py
│   └── api_manager.py          # singleton universal token system
├── telegram_bot/
│   ├── __init__.py
│   └── bot.py                  # long-polling bot
├── github_sync/
│   ├── __init__.py
│   └── gh_sync.py              # GitHub Contents API push
├── android_bridge/
│   ├── __init__.py
│   └── adb_controller.py       # ADB + Termux API (sync + async)
└── skills/
    ├── __init__.py
    ├── orca_skills.py          # single registry, no dupes
    └── shell_executor.py       # whitelisted shell
```

## Setup
```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in tokens
```

## Run
```bash
python orca.py bot       # start Telegram bot
python orca.py sync      # push to GitHub
python orca.py status    # print system status
python orca.py tokens    # list API tokens
python orca.py doctor    # engineering checks
```

## Telegram Commands
- `/start` / `/status` / `/skills` / `/sync` / `/device`
- `/exec <cmd>` / `/token` (generate new)
- `/tap <x> <y>` / `/swipe x1 y1 x2 y2 [ms]` / `/text <msg>`

## Engineering Rules Applied
- **Zero duplication**: each module has a single canonical implementation
- **No Node.js leftovers**: removed all `*.js` and duplicate `telegram.py`/`api_manager.py` clones
- **Singleton APIManager**: every caller shares the same token store
- **Package `__init__.py`**: explicit re-exports, no implicit name collisions
- **Config single-source**: `core/config.py` is the only env reader
- **Doctor self-check**: detects duplicate filenames, oversized files, broken imports
