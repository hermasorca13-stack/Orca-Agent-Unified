# 🐋 Orca Agent — Unified Production System

**Real, working agent connecting Telegram + GitHub + Android (Termux/ADB).**

## Stack
- **Telegram Bot:** `@HermesOrcaXBot` (id 8251930364)
- **GitHub:** `hermasorca13/Orca-Agent-Unified` (master)
- **Android bridge:** ADB + Termux API
- **API:** Universal token system (full permissions `*`)

## Run
```bash
pip install -r requirements.txt
python orca.py bot       # start Telegram bot (long-polling)
python orca.py sync      # push to GitHub
python orca.py status    # print system status
python orca.py doctor    # engineering checks
```

## Files
```
orca-agent/
├── orca.py                     # main entrypoint
├── requirements.txt
├── .env                        # real env (gitignored in production)
├── core/config.py              # single source of env config
├── api_manager/api_manager.py  # universal token mgmt
├── telegram_bot/bot.py         # real bot (long-polling)
├── github_sync/gh_sync.py      # GitHub Contents API push
├── android_bridge/adb_controller.py  # ADB / Termux API
└── skills/                     # plugin skills (no duplicates)
    ├── shell_executor.py
    └── orca_skills.py          # single registry
```

## Tokens
- Bot: `8251930364:AAE2L39B4ltS_vihIePwWpwp0ZuFylngdWo`
- Orca Master: `orca_live_QkZFMmUzOTBHeURKTzJSY1YwSlRINWV3T201N0otSlJkNEdhRjFhaUVINGtn`
- GitHub: set `GITHUB_TOKEN` in `.env` to enable remote sync
