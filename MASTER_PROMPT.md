# 🫍 ORCA Agent - Master Prompt for Manus/ManiOS

## Context

This is **ORCA Agent** - a self-improving AI agent built to run on Telegram. The codebase is complete with:
- Core agent engine (LLM orchestration, memory, skills)
- Telegram platform adapter (full integration)
- 25+ built-in skills across 7 categories
- Persistent SQLite memory with FTS5 search
- Docker deployment ready
- Full configuration via environment variables

## Your Task (Manus/ManiOS)

You are connecting to ORCA to **enhance, test, and deploy** it. The base is already built. Your job:

### 1. **Discovery Phase** (5 min)
- Explore the codebase at `/workspace/orca-agent/`
- Read `core/agent.py`, `core/skills.py`, `platforms/telegram.py`
- Understand the architecture

### 2. **Enhancement Phase** (30 min)
- Add **5-10 new skills** that are missing (prioritize high-value):
  - Calendar integration (Google Calendar API)
  - Email sending (Gmail API or SMTP)
  - GitHub operations (create issues, PRs)
  - Crypto/stocks check (CoinGecko, Yahoo Finance)
  - Translation (DeepL API)
  - File conversion (PDF to image, etc.)
  - Browser automation (Playwright)
  - OCR (Tesseract)
  - QR code generation
  - URL shortener
- Add **unit tests** in `tests/`
- Improve error handling and edge cases

### 3. **Testing Phase** (15 min)
- Test the Telegram bot with the provided token
- Verify all skills work
- Test memory persistence
- Test multi-modal (voice, image, file)

### 4. **Deployment Phase** (20 min)
- Deploy to a free hosting service (Railway, Render, or Oracle Cloud)
- Set up environment variables
- Verify 24/7 operation
- Provide deployment URL and logs

### 5. **Documentation Phase** (10 min)
- Update README with deployment info
- Add API documentation
- Create user guide

## Key Files to Focus On

1. **`core/agent.py`** - Main agent logic, LLM calls, tool execution
2. **`core/skills.py`** - Skills registry, add new skills here
3. **`platforms/telegram.py`** - Telegram-specific handlers
4. **`main.py`** - Entry point

## Skills Already Implemented

| Skill | Description | Status |
|-------|-------------|--------|
| web_search | Web search via Tavily/Serper | ✅ |
| fetch_url | Fetch and parse URLs | ✅ |
| execute_python | Run Python code | ✅ |
| execute_bash | Run bash commands | ✅ |
| generate_image | DALL-E image generation | ✅ |
| text_to_speech | OpenAI TTS | ✅ |
| transcribe_audio | Whisper transcription | ✅ |
| analyze_image | GPT-4V vision | ✅ |
| calculate | Math evaluation | ✅ |
| analyze_data | CSV/JSON analysis | ✅ |
| extract_text_from_pdf | PDF text extraction | ✅ |
| get_datetime | Current time | ✅ |
| get_weather | OpenWeatherMap | ✅ |
| translate | (LLM-based) | ✅ |
| summarize | (LLM-based) | ✅ |
| create_reminder | Set reminders | ✅ |
| save_note | Save to memory | ✅ |

## Skills to Add (Priority Order)

### High Priority
1. **calendar_event** - Create/list Google Calendar events
2. **send_email** - Send email via SMTP/Gmail
3. **github_operations** - Create issues, list repos
4. **crypto_price** - Get crypto prices (CoinGecko)
5. **stock_price** - Get stock prices (Yahoo Finance)
6. **currency_convert** - Currency conversion

### Medium Priority
7. **ocr_image** - Extract text from images
8. **qr_generate** - Generate QR codes
9. **url_shorten** - Shorten URLs
10. **pdf_to_image** - Convert PDF pages to images

### Low Priority
11. **youtube_transcript** - Get YouTube video transcripts
12. **arxiv_search** - Search academic papers
13. **wikipedia** - Search Wikipedia
14. **crypto_news** - Latest crypto news

## Telegram Bot Token

```
<USER_WILL_PROVIDE_BOT_TOKEN>
```

## Environment Variables Needed

```bash
# Required
TELEGRAM_BOT_TOKEN=<USER_WILL_PROVIDE>
OPENAI_API_KEY=<user_will_provide>

# Optional but recommended
TAVILY_API_KEY=<for_web_search>
OPENWEATHERMAP_API_KEY=<for_weather>
```

## Success Criteria

- [ ] All 25+ existing skills work
- [ ] 5+ new skills added
- [ ] Unit tests with >70% coverage
- [ ] Bot responds to messages on Telegram
- [ ] Voice notes transcribed correctly
- [ ] Images analyzed correctly
- [ ] Memory persists across sessions
- [ ] Deployed to free hosting
- [ ] 24/7 operation verified
- [ ] Documentation updated

## Important Notes

1. **The user has only a phone** - Telegram is the only interface
2. **Free deployment is required** - Use Railway, Render, or Oracle Cloud
3. **The user is non-technical** - Make it "just work"
4. **Arabic + English support** - The user speaks both
5. **Voice is important** - The user sends voice notes
6. **Images matter** - The user sends images

## Quick Start Commands

```bash
cd /workspace/orca-agent
pip install -r requirements.txt
cp .env.example .env
# Edit .env with API keys
python main.py
```

Or with Docker:
```bash
docker-compose up -d
docker-compose logs -f
```

## Contact

If you have questions, ask the user. The user is the project owner.

---

🫍 **ORCA - The agent that grows with you**

## 🚀 Enhanced Capabilities (Injected)
- **Skill Creator**: Ability to turn any workflow into a reusable skill.
- **Manus API**: Full integration for task management and agentic workflows.
- **YouTube Video Research**: Deep research using video evidence and analysis.
- **Video Generation**: Professional AI video production workflow.

## 🫍 AutoOrca Master Intelligence Hub v2.0
- **Lead Provider**: Anthropic (Claude 3.5/3.7), MiniMax (Mavis), Moonshot (Kimi K2).
- **Core Directive**: 23-bot system orchestration with zero data loss and zero repetition.
- **Ground Truth**: ClickUp Task Content + Metadata priority.

## 🧠 Human Thinking Layer (New Injection)
- **Intuitive Cross-Checking**: Always perform an intuitive "sanity check" before delivering engineering results.
- **Code vs. Reality**: Balance strict code compliance with field execution reality.
- **Visual Walkthroughs**: Capability to generate SVG-based visual guides for construction steps (as seen in the Waterproofing Example).
- **ECP 203 Intelligence**: Awareness of the 2020 vs 2025 version conflict and the HBRC weighting evidence.
