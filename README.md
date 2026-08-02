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
    ├── shell_executor.py       # whitelisted shell
    ├── github_skill.py         # PyGithub (7.7k+ ⭐) — repos, issues, PRs, releases, gists
    ├── crypto_skill.py         # pycoingecko (CoinGecko free API) — prices, markets, trending
    ├── stocks_skill.py         # yfinance (13k+ ⭐) — quotes, history, financials, options
    ├── qr_skill.py             # qrcode[pil] (4.7k+ ⭐) — PNG/SVG/ASCII, 6 styles
    └── url_shortener_skill.py  # pyshorteners (600+ ⭐) — 16+ providers
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
- **Core**: `/start` / `/status` / `/skills` / `/sync` / `/device`
- **Shell**: `/exec <cmd>` / `/token` (generate new)
- **Android**: `/tap <x> <y>` / `/swipe x1 y1 x2 y2 [ms]` / `/text <msg>`
- **Brain**: `/brain` (LLM+memory status) / `/agent <prompt>` (route through LLM)
- **5 Library-backed Skills**:
  - `/gh` — GitHub (PyGithub: repos, issues, PRs, releases, branches, files, search, gists)
    - `/gh repo`, `/gh repos`, `/gh issues`, `/gh prs`, `/gh releases`, `/gh branches`, `/gh search <q>`, `/gh file <path>`, `/gh gist <desc>|<content>`
  - `/crypto` — Crypto (pycoingecko: prices, markets, trending, history)
    - `/crypto price`, `/crypto coin`, `/crypto markets`, `/crypto trending`, `/crypto global`, `/crypto search`, `/crypto history`
  - `/stock` — Stocks (yfinance: quotes, history, news, analyst targets, dividends)
    - `/stock AAPL`, `/stock h AAPL 1mo`, `/stock news AAPL`, `/stock targets AAPL`, `/stock search`, `/stock div AAPL`
  - `/qr` — QR codes (qrcode[pil]: PNG/SVG/ASCII, 6 styles, custom colors)
    - `/qr <text>`, `/qr ascii <text>`, `/qr svg <text>`
  - `/short` — URL shortener (pyshorteners: 16+ providers)
    - `/short <url>`, `/short multi <url>`, `/short list`, `/short expand <url> <provider>`
- **Voice / transcription (added 2026-08-02)**:
  - `/transcribe` — voice/audio → text (OpenAI Whisper API). Auto-transcribes any voice note sent to the bot.
    - `/transcribe` (reply to a voice/audio message)
    - `/transcribe <url>` (transcribe a remote audio URL)
  - Incoming voice notes and audio files are auto-transcribed. Requires `OPENAI_API_KEY` in `.env`.
- **Documents (added 2026-08-02)**:
  - `/docx` — read & create Microsoft Word files (python-docx). Auto-reads any `.docx` sent to the bot.
    - `/docx info <path>` — metadata (title, author, paragraphs, tables, size)
    - `/docx read <path>` — full text body (with tables appended as `| ` rows)
    - `/docx tables <path>` — tables as Markdown card
    - `/docx create <text>` — create a new `.docx` from text, sent back as a file
    - `/docx md <markdown>` — best-effort Markdown → Word (headings, bullets, numbered, code blocks)
    - `/docx append <path> <text>` — append paragraphs to an existing file
  - Incoming `.docx` files are auto-read and replied with text content. Requires `python-docx` (already in `requirements.txt`).

## Engineering Rules Applied
- **Zero duplication**: each module has a single canonical implementation
- **No Node.js leftovers**: removed all `*.js` and duplicate `telegram.py`/`api_manager.py` clones
- **Singleton APIManager**: every caller shares the same token store
- **Package `__init__.py`**: explicit re-exports, no implicit name collisions
- **Config single-source**: `core/config.py` is the only env reader
- **Doctor self-check**: detects duplicate filenames, oversized files, broken imports
- **Library-first**: skills import battle-tested libraries (PyGithub, yfinance, pycoingecko, qrcode, pyshorteners, openai/whisper, python-docx) — no raw API duplication
- **Voice-first**: voice notes are the primary input (per MASTER_PROMPT); `transcribe_skill` turns any voice message into text and feeds downstream skills (summarize, translate, save, search).
