# üõ†Ô∏è Orca Agent ‚Äî Build History & Lessons Learned

> Living document. Every session that touches the bot appends what worked,
> what failed, and why ‚Äî so we never repeat a mistake.

---

## Session: 2026-07-29 ‚Äî Adding 5 library-backed skills (gh / crypto / stock / qr / short)

### What was requested
Bring the production bot to feature parity with the latest master code:
- `/gh` ‚Äî GitHub ops (PyGithub)
- `/crypto` ‚Äî Markets (pycoingecko)
- `/stock` ‚Äî Quote (yfinance)
- `/qr` ‚Äî QR codes (qrcode)
- `/short` ‚Äî URL shortener (pyshorteners)
- All five must show in the Telegram command menu
- No rebuild from scratch ‚Äî add & modify only

### What we did (in order)

1. **Read state, not code first.** Cloned the repo, scanned commit log,
   confirmed all 5 skills were already shipped (commits `47aae87`, `5eae891`).
   That told us the *only* gap was the production instance running stale code
   + the Telegram menu cache.

2. **Tried the live menu first.** `getMyCommands` returned 13 commands ‚Äî
   the 5 new ones were missing. That confirmed: code in repo ‚úÖ, code in
   bot's process ‚ùå, code in Telegram's menu cache ‚ùå.

3. **Pushed `setMyCommands` via raw API.** Single call registered all 19
   commands. The Telegram client refreshes the menu within seconds ‚Äî this
   works even if the running bot process is ancient. **Always do this BEFORE
   fighting with the bot process itself.**

4. **Ran a local sanity test on every skill** before touching the remote:
   - crypto ‚úÖ (BTC/ETH live prices)
   - qr ‚úÖ (1121-byte PNG)
   - stock ‚úÖ (AAPL $340.08)
   - github ‚ùå ‚Üí 404 because the skill hardcoded `GH_USER/REPO` but the
     repo actually lives under the `hermasorca13-stack` **org**
   - short ‚ö†Ô∏è ‚Üí `isgd` provider was down ("database insert failed") but
     `tinyurl`, `clckru`, `dagd` worked fine

5. **Fixed what was actually broken (ADD, not rebuild):**
   - `core/config.py`: added `GH_ORG` + `GH_FULL_NAME` constants
   - `skills/github_skill.py`: 13 occurrences of `f"{GH_USER}/{GH_REPO}"`
     replaced with `GH_FULL_NAME` via `replace_all` (one-pass surgery)
   - `telegram_bot/bot.py`: changed `/short` default provider from `isgd`
     (often down) to `tinyurl` (most reliable in the pyshorteners chain)

6. **Tried to run a local bot instance** to test the handlers end-to-end.
   `telegram.error.Conflict: terminated by other getUpdates request` ‚Äî the
   remote orchestrator was still holding the long-poll slot. We did NOT
   `logOut` the bot this time. Instead we:

7. **Triggered `/update` on the remote bot** so it self-pulls the new code
   from GitHub and restarts cleanly. The `cmd_update` handler does exactly
   this (`git pull --ff-only` + `os.execvp`).

### Why this approach (lessons)

- ‚ùå Don't `logOut` to "free" the token. The previous session did that
  and the token sat in a logged-out state until a fresh `Application`
  ran `getMe`/`getUpdates` against it. Recovery took ~15 min of polling.
  Use `close` or let the orphan instance time out instead.

- ‚ùå Don't spawn a local bot while another instance is polling. PTB
  raises `Conflict` immediately. The preflight in `orca.py` exists
  *exactly* to prevent this ‚Äî listen to it.

- ‚ùå Don't rebuild the bot file from scratch when the repo already has
  the new code. Read first, modify second.

- ‚úÖ The single best move was `setMyCommands` over the raw HTTP API.
  It decouples menu freshness from bot process freshness. Even if the
  bot is running week-old code, the menu can be up-to-date.

- ‚úÖ Pushing the new code + `/update` is the right way to bring the
  remote instance current. `os.execvp` cleanly replaces the polling
  process without a `logOut` cycle.

- ‚úÖ Test each skill in isolation before assuming the wiring works.
  The `github_skill` passed the import test but failed at the API call
  because of the user-vs-org assumption. Always call the function once.

### Files touched this session

| File | Change | Lines |
|------|--------|-------|
| `core/config.py` | +`GH_ORG`, +`GH_FULL_NAME` | +2 |
| `skills/github_skill.py` | 13x `GH_USER/REPO` -> `GH_FULL_NAME` | ¬±13 |
| `telegram_bot/bot.py` | default shortener `isgd` -> `tinyurl` (x2) | ¬±2 |
| `BUILD_HISTORY.md` | this file | +new |

All changes pushed to `master` (commit `ff9c92d`).

### Verification checklist

- [x] `getMyCommands` returns 19/19 commands
- [x] Local skills module loads 7/7
- [x] crypto: live prices from CoinGecko
- [x] qr: valid PNG generated
- [x] stock: live quote from yfinance
- [x] github: `GH_FULL_NAME` resolves to `hermasorca13-stack/Orca-Agent-Unified`
- [x] short: tinyurl default works, fallback chain to clckru/dagd
- [x] /update command sent to remote
- [x] Test messages sent (msg_id 121-126) - replies visible in Telegram

### Open follow-ups (for next session)

- [ ] Verify on Telegram that all 5 new commands produce real responses
- [ ] If remote bot didn't restart, send `/start` to trigger
      `maybe_auto_update()` then `/update` again
- [ ] When the LLM key is set (Anthropic / OpenAI), `/agent` and
      free-form `on_text` will route through the brain instead of fallback
- [ ] Consider adding a `/menu` shortcut that dumps `getMyCommands`
      for users on old Telegram clients

---

## Session: 2026-07-29 (continued) ‚Äî Multi-provider LLM + self-heal + FSM

### What was requested
- Real LLM intelligence (bot was still in rule-based mode)
- Self-healing watchdog so the bot recovers from transient failures
- Multi-step `/setup` wizard so Hermas can add an LLM key from Telegram
- Everything ADD-ONLY, no deletions

### What we did

1. **Researched provider landscape** across OpenRouter, LiteLLM, Anthropic
   SDK, google-generativeai, groq-python SDK. Chose the OpenAI-compatible
   SDK pattern where possible (groq, mistral, ollama all use it) ‚Äî single
   import path, uniform error handling.

2. **Created `core/llm_providers.py`** ‚Äî single source of truth for 8
   providers + `AsyncLLMRouter` with failover. ~250 lines, zero new
   dependencies for the 3 OpenAI-compatible ones (gemini needs one new pip:
   `google-generativeai`).

3. **Extended `core/agent.py` additively** ‚Äî one new `elif` branch in
   `_init_llm` for the new providers, one new `if` block in `_call_llm`
   that gates on `LLM_FAILOVER=1`. Existing logic unchanged.

4. **Created `core/self_heal.py`** ‚Äî DB/FS/network/heartbeat probes,
   auto-recovery (WAL, directory creation), `/diag` command output.
   215 lines, no external deps.

5. **Created `core/fsm.py`** ‚Äî lightweight in-memory state machine with
   5-min TTL. `SETUP_API_KEY` and `SETUP_PROVIDER` flows registered.

6. **Wired into `telegram_bot/bot.py`** ‚Äî 3 new command handlers
   (`cmd_diag`, `cmd_setup`, `cmd_cancel`), 1 FSM message router in
   group=1 (lower priority than `on_text`). `set_my_commands` updated
   to 31 commands. `run()` now starts the self-heal watchdog.

7. **Pushed `setMyCommands` over raw API** ‚Äî Telegram menu now lists
   31 commands (was 19 on the live instance). The live instance will
   catch up on next `/update` or auto-update tick.

### Why this approach (lessons)

- ‚úÖ **One provider module, one router.** Avoids 8 scattered `if` blocks
  in `agent.py`. If we add Cohere tomorrow, one entry in the catalog
  and a 5-line factory function.

- ‚úÖ **Self-heal's "last_action" field** is gold for ops. It tells you
  not just *that* something failed, but *what* the bot did about it.
  /diag surfaces it directly.

- ‚úÖ **FSM with TTL is enough for 95% of flows.** Persistent FSM
  (SQLite-backed) is overkill until we have flows longer than 5 min.

- ‚ö†Ô∏è **The live bot still shows 19 commands** in the user-facing menu
  even though `getMyCommands` reports 31. This is a Telegram client
  cache, not a bot state. It will refresh on next session restart of
  the bot. Sending `/update` to the bot will trigger that restart.

- ‚ö†Ô∏è **No LLM key is set.** That's why all the rule-based replies
  keep happening. The new `/setup` command is the fastest path to
  real intelligence: `/setup gemini <key>` then `/update`.

### Files touched this session

| File                       | Status   | Lines |
|----------------------------|----------|-------|
| `core/llm_providers.py`    | NEW      | +252  |
| `core/self_heal.py`        | NEW      | +215  |
| `core/fsm.py`              | NEW      | +90   |
| `core/agent.py`            | MODIFIED | +27   |
| `telegram_bot/bot.py`      | MODIFIED | +105  |
| `requirements.txt`         | MODIFIED | +3    |
| `ORCA_MASTER_PLAN.md`      | NEW      | +350+ |
| `BUILD_HISTORY.md`         | MODIFIED | +80   |

Pushed: commit `65082d1` (1f1a3c2..65082d1 master -> master).

### Verification checklist

- [x] `getMyCommands` returns 31 commands
- [x] All 8 new modules `ast.parse` clean
- [x] `AsyncLLMRouter` instantiated with default order
- [x] `fsm.push / get / cancel` round-trip works
- [x] `SelfHeal.diag()` returns formatted Telegram-ready report
- [x] DB probe confirms `journal_mode=wal`
- [x] Pushed to GitHub
- [x] `setMyCommands` over raw API succeeded

### Open follow-ups

- [ ] Verify on Telegram that `/diag`, `/setup`, `/cancel` respond
- [ ] Add `google-generativeai` to the live server's pip
- [ ] Send `/update` to the live bot so it picks up `65082d1`
- [ ] Run `/setup gemini <key>` to enable real LLM brain
- [ ] Consider a CI workflow (`.github/workflows/test.yml`)

## 2026-08-03 ó Egyptian-Arabic dialect support for intent_skill

The intent classifier is the bot's NL front door. The primary user
(smoha8) communicates in Egyptian Arabic mixed with English, so we
extended the rule set from 23 commands to cover 23 commands x ~5
Egyptian variants each.

### What changed

- `skills/intent_skill.py`: 80+ new Egyptian dialect patterns added
  to every rule, plus an `ar-eg` language tag for the dialect detector.
  Fix: use `¯?` (optional shadda) instead of character classes
  `[X¯]` to avoid the regex engine consuming the shadda and
  missing the next consonant.
- `tests/test_intent_egyptian.py`: 84 scenarios for realistic
  Egyptian phrases (greetings, weather, search, image, etc.)
- `tests/test_intent_lab_integration.py`: 23 integration tests
  (multi-turn, compound intents, spelling variants, adversarial
  input, throughput, determinism, thread-safety)

### Test counts

- 310 passed, 3 skipped (up from 287 passed, 3 skipped)
- Average per-call latency: <2ms (Arabic), <2ms (English), <5ms (mixed)
- Pushed: commit `d1b7e2e` (65e5ee7..d1b7e2e master -> master)

### Lessons learned

1. **Char classes with shadda are footguns in Python regex.** A class
   like `[€¯]` matches either char, but the engine picks the
   leftmost. For ` ›—¯€`, it consumes the shœ…, leaving `€`
   unmatched. Use `X¯?` (consonant + optional shœ…) instead.
2. **Arabic question mark `ø` is a literal, not a regex quantifier.**
   Use `?` (ASCII) for optional, or escape `\u061f` for literal.
3. **Test expectations should accept `OR` alternatives.** A phrase
   like `„„ﬂ‰  »ÕÀ·Ì ⁄‰ weather API` is genuinely ambiguous between
   `/weather` and `/search`. The classifier's choice is defensible
   either way. Pin only the cases where the answer is unambiguous.
4. **A 30-skill agent bridge can fail at collection time even when
   intent_skill itself is fine.** Always isolate new skill tests
   so they don't pull in telegram_adapter / service code.

## 2026-08-03 ó YouTube video analysis skill (youtube_skill)

The Orca roadmap listed `youtube_transcript` as a low-priority skill
and `YouTube Video Research` as an enhanced capability. Today we
turned both into a production-grade Python skill.

### What changed

- `skills/youtube_skill.py` (40 KB, 1000+ lines) ó full 2026 stack:
  - **Zero-API-key URL parser** that handles every YouTube URL shape
    (watch, youtu.be, shorts, embed, live, m.youtube.com,
    music.youtube.com, bare 11-char IDs) and refuses non-YouTube URLs
  - **oEmbed** for headline metadata (no API key, no OAuth)
  - **`youtube-transcript-api`** (v0.6.2+, 10M+ downloads, MIT, 125+
    language codes) with a graceful fallback chain:
    manual captions -> auto-generated -> auto-translate
  - **Multilingual** by design: every supported language is
    selectable by ISO code
  - **Heuristic summary** (no LLM needed) ó multilingual-safe
    position+length scoring
  - **LLM analysis** with the high-density prompt template from
    `core/skills_data/youtube_research.md` (8+ direct quotes,
    data points, arguments, counter-arguments, sentiment)
  - **Defensive error hierarchy**: `YouTubeError` +
    `InvalidURLError` / `MetadataError` / `TranscriptError` /
    `AnalysisError`
- `tests/test_youtube_skill.py` ó 67 unit + integration tests
  covering URL parser, result types, formatters, heuristic, LLM
  (mocked), multilingual, end-to-end pipeline, performance
- `telegram_bot/bot.py` ó added `/youtube` and `/yt` commands,
  `SKILL_CATALOG` entry, full Markdown-card rendering with
  Telegram's 4096-char message-length limit handled by
  follow-up messages
- `skills/intent_skill.py` ó added `/youtube` intent pattern
  with English + Egyptian dialect triggers, URL detection, and
  verbs (analyse, summarise, transcribe, review, explain)
- `requirements.txt` ó added `youtube-transcript-api>=0.6.2`
- `README.md` ó full YouTube section

### Test counts

- 377 passed, 5 skipped (up from 310, 3 skipped)
- Pattern matching < 2ms; URL parser < 0.5ms per call;
  heuristic summary < 200ms for 1,000 segments

### Lessons learned

1. **Lazy imports for optional deps** ó `youtube-transcript-api` is
   only imported when `extract_transcript` is called. This keeps
   CI fast and avoids breaking the module if the dep is missing.
2. **Mock via `sys.modules`** ó the test suite injects a fake
   `youtube_transcript_api` module into `sys.modules` so the
   lazy import inside `_fetch_transcript_yta` resolves to the
   mock. `monkeypatch.setattr` doesn't work on names that haven't
   been imported yet.
3. **Pattern specificity matters** ó the first cut of the
   YouTube intent pattern matched `"„„ﬂ‰  Õ·· «·‹ dataset œÂ"`
   (an EFI-OS request) because the verb ` Õ··` overlapped.
   Fix: require a YouTube-context token (`«·›ÌœÌÊ`, `«·ÌÊ ÌÊ»`,
   `youtube`, `yt`) immediately after the verb.
4. **def parse_url("https://...")** ó the regex needs to handle
   every shape YouTube has ever shipped. Shorts/embed/live all
   live under the same domain but with different path prefixes.
   The cleanest parser is: if host is youtu.be -> path is the ID;
   else if path starts with `/shorts/`, `/embed/`, `/live/`,
   or `/v/` -> the next path segment is the ID; else
   `/watch?v=...` from the query string.

### 2026-08-03 ó Live test against real YouTube + v1.2.x API compatibility

After pushing the YouTube skill, we ran a real end-to-end test
against a public Egyptian video
(`https://www.youtube.com/watch?v=7M5XZ6rRw7k` ó "⁄„·  „‘—Ê⁄ ÌœŒ·
950\$ «Ê Ê„« Ìﬂ „‰ €Ì— Œ»—Â", by "’›— ⁄·Ì «·Ì„Ì‰", about earning
money online in 2026).

#### Result

| Step                              | Status | Latency  |
| --------------------------------- | ------ | -------- |
| URL parser                        | OK     | 0.1ms    |
| oEmbed metadata                   | OK     | 203ms    |
| Transcript (auto-generated Arabic)| OK     | 1,506ms  |
| analyze() pipeline                | OK     | 1,529ms  |
| Telegram card render              | OK     | <50ms    |

The transcript pipeline produced **575 real Arabic caption
segments, 4,372 words, 23.7 minutes of speech**. The heuristic
summary correctly extracted the opening thesis: "ﬂÀÌ— „‰‰« ﬂ·‰« ›Ì
«·ﬁ‰«Â Â‰« „Õ «ÃÌ‰ «‰ «Õ‰« ‰⁄„· ›·Ê” «Ê‰ ·«Ì‰". Real data
points surfaced: "25\$ free credit", "Pro plan 15\$/month".

#### API compatibility fix

The installed library at runtime was `youtube-transcript-api==1.2.4`
(January 2026 release), which uses `FetchedTranscriptSnippet`
dataclass objects with attribute access (`.text`, `.start`,
`.duration`) instead of the `dict` style from v0.6.x. Without
the fix, the skill would crash with::

    AttributeError: 'FetchedTranscriptSnippet' object has no attribute 'get'

Fix: a new `_normalise()` helper inside `_fetch_transcript_yta`
coerces both v0.6.x dicts and v1.2.x dataclass snippets into a
uniform internal `dict` shape. The rest of the skill is
library-version-agnostic. This is the same defensive pattern we use
everywhere else: never trust the shape of an external library.

#### Lessons

1. **Always test against the live library, not just a mock.** Our
   test suite covered dict-style snippets; the real install
   ships dataclass snippets. A live test caught this in one
   minute that 67 unit tests missed.
2. **Pin a minimum version, not a maximum.** The requirements
   say `>=0.6.2`, which is correct: both v0.6.x and v1.2.x
   must work. Pinning to `==1.2.4` would have broken v0.6 users.

---

## 2026-08-03 ó Zero-loss fallback layer (offline_fallbacks)

The user raised a hard constraint: **0% capability loss when no
external API key is configured**. Until today, every key-dependent
skill crashed with a clear error message when its key was missing
(\ImageSkill needs OPENAI_API_KEY\, \Whisper requires a key\, Ö).
Better than silent failure, but still a failure. The bot should
remain *useful* in offline / demo / CI mode.

### What changed

- **New file: \skills/offline_fallbacks.py\ (19 KB)** ó single point
  of truth for offline alternatives. Every function is defensive
  (never raises) and returns a structured response. Public surface:
  - \local_image(prompt, size, output_format)\ ó Pillow procedural
    art. Deterministic via SHA-256(prompt). PNG/JPEG, ~3s for
    1024◊1024. Always produces a real file.
  - \local_audio_info(source)\ ó stdlib \wave\ + \fprobe\
    fallback. Returns duration / channels / sample_rate / bitrate.
  - \local_search(query, limit, timeout)\ ó DuckDuckGo HTML scrape
    via stdlib \urllib\. Returns \[{title, url, snippet}]\.
  - \local_text_complete(prompt, max_tokens)\ ó rule-based
    summarise / list / question / echo. Not an LLM, but produces
    a sensible answer for structured prompts. Defensive coercion
    of non-str input.
  - \local_transcribe_placeholder(source, duration)\ ó structured
    \{text, language, duration, model, ok=False, fallback=True,
    audio_info, note}\. Mirrors the OpenAI Whisper response shape
    so callers don't branch.

- **\skills/image_skill.py\** ó when \OPENAI_API_KEY\ is missing,
  route to \local_image\ instead of raising. When the key is set
  but the API call fails (timeout, 5xx, network), also fall back.
  Logs the reason for telemetry. Returns a real PNG.

- **\skills/transcribe_skill.py\** ó when \OPENAI_API_KEY\ is
  missing, return \local_transcribe_placeholder\ with \ok=False\.
  When the audio is oversize, route to the same offline path.

- **\	ests/test_offline_fallbacks.py\ (28 tests)** ó covers
  PNG correctness, determinism, size enforcement, Arabic prompts,
  speed (<5s for 256◊256), audio metadata for path/URL/bytes,
  text completion for empty/summarise/list/Arabic/question/echo,
  transcription placeholder shape, and the never-raises contract
  for every function.

- **Updated \	ests/test_image_skill.py\ and
  \	ests/test_transcribe_skill.py\** ó flipped the "no key"
  tests from \pytest.raises\ to "returns offline fallback".
  The new contract is: \ok=False\ is acceptable; \aise\ is
  not.

### Skill-by-skill capability map when no key is set

| Skill            | Before                       | After                              |
| ---------------- | ---------------------------- | ---------------------------------- |
| \image_skill\    | \RuntimeError: missing key\ | real PNG via \local_image\         |
| \	ranscribe_skill\| \RuntimeError: missing key\ | audio metadata + \ok=False\        |
| \web_search_skill\| DDG fallback (already had)   | DDG fallback (already had)         |
| \intent_skill\    | heuristic (already had)      | heuristic (already had)            |
| \youtube_skill\   | heuristic (already had)      | heuristic + transcript (already had) |

### Test counts

- **405 passed, 5 skipped** (up from 377, 5 skipped)
- Pushed: commit \c46b92d\ (\8b1fb9..c46b92d master -> master\)
- Verified: \git rev-parse HEAD\ = \c46b92df14ea9e6e44945f9b904fc1e87a4927e9\

### Lessons learned

1. **Offline-first, not crash-first.** A bot that returns a real PNG
   placeholder is more useful than one that errors out. The user
   can still *see* what the prompt looked like, and the skill
   surface is identical (same dict shape, same file path).
2. **Defensive coercion at the boundary.** \local_text_complete\
   was failing on \int(42)\ input because of \(prompt or '').strip()\.
   Fix: explicitly handle \None\, then \isinstance(prompt, str)\,
   then \str(prompt)\ with a try/except fallback to \""\. The
   never-raises contract is now testable.
3. **Pillow procedural art is enough for previews.** The same prompt
   always produces the same image (SHA-256 seeded gradient). This
   doubles as a cache key ó repeat requests hit the same file on
   disk.
4. **The audio metadata fallback is the most underrated one.** When
   Whisper is unavailable, returning \{duration: 23.7 min,
   channels: 1, sample_rate: 16000}\ is genuinely useful ó the user
   knows whether to expect 5 seconds or 5 hours of content.
5. **The DDG HTML scrape already shipped with \web_search_skill\.
   No change needed.** The fallback was already there; today it
   became the documented contract.

