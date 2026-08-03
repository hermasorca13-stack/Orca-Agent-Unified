# 🐋 Orca Agent — Unified Production

Real, working agent: **Telegram + GitHub + Android bridge + Universal API** in one clean Python package. No duplicates, no Node.js leftovers, single source of truth.

> 📍 **Canonical location: `D:\ORCA AGENT\Orca-Agent-Unified\`** (per user request 2026-08-03).
> Do not clone or copy to any other path. See `CANONICAL_LOCATION.txt` for details.
>
> ⚠️ **Local-only project**: no GitHub, no remote, no cloud copy. See `LOCAL_ONLY_NO_REMOTE.txt`.

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
  - `/xlsx` — read & create Microsoft Excel files (openpyxl). Auto-reads any `.xlsx`/`.xlsm` sent to the bot.
    - `/xlsx info <path>` — workbook metadata (sheets, cells, creator, modified)
    - `/xlsx sheets <path>` — list of sheet names
    - `/xlsx read <path> [sheet]` — first 25 rows of a sheet as a Markdown table
    - `/xlsx cell <path> <sheet> <ref>` — single cell value (e.g. `B2`)
    - `/xlsx create <h1,h2,h3> | <v1,v2,v3> | ...` — create a new `.xlsx`, returned as a file
    - `/xlsx append <path> <sheet> <v1,v2,...>` — append a row
    - `/xlsx set <path> <sheet> <ref> <value>` — write a single cell (int / float / bool auto-detected)
  - Incoming `.xlsx`/`.xlsm` files are auto-read and replied with a Markdown table of the first sheet. Requires `openpyxl` (already in `requirements.txt`).
  - `/search` — multi-provider web search (Tavily → Serper → DuckDuckGo fallback). Foundation skill for research, fact-check, summarization.
    - `/search <query>` — top 5 results
    - `/search <query> -n 10` — top 10 results
    - `/search <query> -p tavily` — force a specific provider
    - `/search <query> -t 30` — custom timeout
  - `TAVILY_API_KEY` is recommended (best results). `SERPER_API_KEY` is a backup. Falls back to DuckDuckGo (no key, limited). Requires `tavily-python` (already in `requirements.txt`).
  - `/image` — text-to-image via DALL-E 3 (or DALL-E 2). Closes the multimodal loop with `/transcribe`.
    - `/image <prompt>` — generate a 1024×1024 standard image
    - `/image <prompt> -s 1792x1024` — landscape
    - `/image <prompt> -s 1024x1792 -q hd` — portrait, HD quality
    - `/image <prompt> -m dall-e-2` — cheaper, legacy model
  - Requires `OPENAI_API_KEY` in `.env` (already used by `/transcribe`). Cost: ~$0.04 (DALL-E 3 standard 1024²), ~$0.08 (HD), ~$0.12 (1792²).
- **YouTube video analysis (added 2026-08-03)**: `/youtube` understands any YouTube URL shape (`watch?v=`, `youtu.be/`, `shorts/`, `embed/`, `live/`, `m.youtube.com`, `music.youtube.com`, or even a bare 11-char ID) and returns metadata (title, author, thumbnail) + full transcript in 125+ languages + summary + key quotes + topics + entities + data points. Pipeline:
    1. **oEmbed** for headline metadata (no API key)
    2. **`youtube-transcript-api`** for the full transcript, with a graceful fallback chain: manual captions → auto-generated captions → auto-translate via YouTube's built-in caption-translation service
    3. **LLM** (when `OPENAI_API_KEY` is set) for structured analysis using the high-density prompt template from `core/skills_data/youtube_research.md`; otherwise a heuristic extractive summary
    - `/youtube <url>` — full analysis card
    - `/youtube <url> en,ar` — prefer English then Arabic caption track
    - `/yt <url>` — alias
  - Cost: $0 with no LLM key; ~$0.01 per video with `OPENAI_API_KEY` (gpt-4o-mini analysis). Requires `youtube-transcript-api` (already in `requirements.txt`).
- **PDF (extended 2026-08-02)**: `/pdf` now writes too (text → PDF, markdown → PDF) and can OCR scanned pages.
    - `/pdf info <path>` — metadata (unchanged)
    - `/pdf text <path> [page]` — extract text (unchanged)
    - `/pdf tables <path> [page]` — extract tables (unchanged)
    - `/pdf make <text>` — generate a PDF from plain text, returned as a file
    - `/pdf md <markdown>` — best-effort Markdown → PDF (headings, bullets, code blocks, inline bold/italic/code)
    - `/pdf ocr <path> [page]` — OCR a scanned PDF page; requires Tesseract + poppler on the system
  - Generation uses `reportlab` (no native deps). OCR uses `pdf2image` + `pytesseract` (already in `requirements.txt`).
- **EFI-OS (added 2026-08-02)**: `/efi` is a thin Telegram wrapper around the bundled local evidence OS.
    - `/efi capabilities` — show the 17-capability matrix
    - `/efi self-test` — run the 19 bundled integrity tests
    - `/efi research <query>` — local RAG research (no API keys)
    - `/efi analyze <subject>` — engineering analysis (17 lenses)
    - `/efi compare <sub1> <sub2> [...]` — rank shared/different principles
    - `/efi ingest <subject> <local-path> [type]` — ingest a local file
  - The wrapper at `skills/efi_os_skill.py` shells out to `tools/EFI_OS.py` and verifies its SHA-256 on import (refuses to run a tampered file). Uses NO external API keys; all data stays on the bot host. 19/19 bundled self-tests pass.
- **Intent (added 2026-08-02)**: `/intent` understands free-form Arabic / English / mixed messages and maps them to the closest Orca command.
    - `/intent ابحث عن weather in Tokyo` → suggests `/search weather in Tokyo`
    - `/intent اعمل صورة قطة في الفضاء` → suggests `/image قطة في الفضاء`
    - `/intent translate this to Arabic` → suggests `/translate this to Arabic`
  - Hybrid 2026 stack: deterministic pre-compiled patterns (always works, no API key) + optional LLM refinement for low-confidence matches (uses the existing LLM bridge with the user's command history as in-context examples). 23 commands covered. Arabic + English + mixed-language detection. Per-user history (rolling 10 commands) used as few-shot examples.
  - The `on_text` fallback also runs intent classification when the LLM brain is offline, so the user still gets "Did you mean /weather Cairo?" instead of a generic "I don't understand".
  - 43 unit tests cover pattern matching, language detection, entity extraction, user profile, LLM refinement paths, error handling.

## Engineering Rules Applied
- **Zero duplication**: each module has a single canonical implementation
- **No Node.js leftovers**: removed all `*.js` and duplicate `telegram.py`/`api_manager.py` clones
- **Singleton APIManager**: every caller shares the same token store
- **Package `__init__.py`**: explicit re-exports, no implicit name collisions
- **Config single-source**: `core/config.py` is the only env reader
- **Doctor self-check**: detects duplicate filenames, oversized files, broken imports
- **Library-first**: skills import battle-tested libraries (PyGithub, yfinance, pycoingecko, qrcode, pyshorteners, openai/whisper, python-docx, openpyxl) — no raw API duplication
- **Voice-first**: voice notes are the primary input (per MASTER_PROMPT); `transcribe_skill` turns any voice message into text and feeds downstream skills (summarize, translate, save, search).
