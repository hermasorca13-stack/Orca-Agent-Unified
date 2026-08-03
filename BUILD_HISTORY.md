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


---

## 2026-08-03 ó Multi-provider search chain (DDG -> Wikipedia)

After the offline fallback commit (\c46b92d\), the live DDG smoke
test returned 0 results for every query. The 2026 DDG HTML endpoint
serves an **anomaly modal** challenge for nearly every bot-like
User-Agent (\"Unfortunately, bots use DuckDuckGo too\"). Our existing
\_ddg_search\ would parse this page and return 0 real results
silently.

The user's standing rule is **0% loss of capability when no API key**.
So we needed a second leg of the chain that works in 2026.

### What we tried

- **DDG HTML** (legacy \html.duckduckgo.com/html/\) ó blocked by
  anomaly detector (12 KB of \"verification required\" HTML)
- **DDG lite** (\lite.duckduckgo.com/lite/\) ó same block
- **Brave** (\search.brave.com/search\) ó HTTP 429 too many requests
- **Qwant API** ó HTTP 403 forbidden
- **Mojeek** ó captcha (ALTCHA challenge) on the HTML endpoint
- **Startpage** ó Anubis challenge (heavy anti-bot)
- **SearXNG (searx.be)** ó returns HTML, not the JSON we asked for
- **Bing** ó not probed (would need user-agent work)
- **Wikipedia REST** (\/w/api.php?action=query&list=search\) ó **works**
  Real results, no captcha, no key, JSON response, multilingual
  via \{lang}.wikipedia.org\

### What changed

- \skills/offline_fallbacks.py\: \local_search\ is now a chain
  - \_ddg_search()\ ó first attempt, detects the anomaly page
    (\nomaly-modal\ in body) and returns \[]\ cleanly
  - \_wikipedia_search()\ ó second attempt via MediaWiki
    \ction=query&list=search\. Strips the
    \<span class=\"searchmatch\">\ HTML, builds a stable
    \wikipedia.org/wiki/Title\ URL
  - \local_search()\ ó tries each provider, returns the first
    non-empty list, never raises
- Each provider is a separate function so callers can pick a
  specific backend (e.g. web_search_skill can call
  \_wikipedia_search\ directly for known entities).
- \	ests/test_offline_fallbacks.py\: new TestWikipediaSearch
  and TestDDGSearch classes (4 new tests, total 32).

### Live verification

3 real queries, all returned 5 results from Wikipedia in ~750ms
per query:

| Query                   | Source     | Hits | Sample result                                |
| ----------------------- | ---------- | ---- | -------------------------------------------- |
| python tutorial 2026    | wikipedia  | 5    | Python (programming language)                 |
| egyptian arabic NLP     | wikipedia  | 5    | Egyptian Arabic, Varieties of Arabic          |
| orca agent unified      | wikipedia  | 5    | (best-effort hits in FOSS / Consciousness)   |

Total: 409 passed, 5 skipped.
Pushed: commit \7e97aaa\ (\ed31385..7e97aaa master -> master\).
Verified: \git rev-parse HEAD\ = \7e97aaa34ee5be7c8296a72353793c40ff3dc490\.

### Lessons learned

1. **The 2026 search landscape is hostile to bots.** DDG, Mojeek,
   Startpage, Brave, Qwant all have anti-bot protection that
   blocks simple \urllib\ clients. Wikipedia is the last
   major open search backend that doesn't.
2. **Multi-provider chains are the only sustainable answer.**
   When one provider is down or blocking, fall through to the
   next. The user should never see an empty result list when
   *any* provider is reachable.
3. **Anomaly detection is detectable in the body.** DDG's
   challenge page is identifiable by \nomaly-modal\ class or
   the literal \"Unfortunately, bots use DuckDuckGo too\". Detecting
   this and returning \[]\ is better than trying to parse
   captcha HTML as search results.
4. **Wikipedia is narrow but reliable.** It works for entities
   (people, places, languages, software, scientific concepts)
   and fails silently for ephemeral queries (weather, news,
   \"what is the best X in 2026\"). That's the right tradeoff
   for an offline fallback ó better to have 5 good results for
   the things it knows than 0 spam results.
5. **Don't remove the dead provider.** DDG might still work
   from whitelisted IPs or after cookies. The chain costs
   nothing extra; we keep it as the first attempt.

---

## 2026-08-03 ó Orca <-> Termux bidirectional bridge

The user asked: *\"⁄«Ì“ «·ÊﬂÌ· » «⁄Ï orca agent œ«Œ· ÃÌ  Â» Ì „ «‰‘«¡
« „ … «Ê Ã”— „»«‘— »Ì‰… Ê»Ì‰ termux in my desktop\"*. In other
words: build an automation / direct bridge between the Orca
Telegram bot and a phone (or desktop) running Termux.

### Goal

Let the user control their **phone** from anywhere in the world
through the Orca Telegram bot. The phone does not need a public
IP, port forwarding, or its own Telegram bot.

### Architecture (2026 stack)

`
Telegram user
     ?
     ?
???????????????????????????????         ????????????????????????
? Orca Bot (this repo)        ?         ? Termux on phone      ?
?  skills/termux_skill.py     ????HTTP????  tools/termux_bridge ?
?  tools/termux_server.py     ?  poll   ?    (Python daemon)   ?
?   FastAPI on :8765          ?  3s     ?  Termux:API + shell  ?
?   + JSONL queue             ?         ????????????????????????
???????????????????????????????
`

Transport: **HTTP polling every 3s** (chose over WebSocket/MQTT/SSH
because it works through any NAT, no tunnel needed, easy to debug
with curl, ~1s typical latency).

### What changed

- **\	ools/termux_server.py\ (17 KB)** ó Orca-side FastAPI app:
  - Bearer-token auth (TERMUX_BRIDGE_TOKEN env var)
  - 7 HTTP endpoints: \/health\, \/pending\, \/command\,
    \/result\, \/result/{id}\, \/event\, \/events\, \/status\
  - File-based JSONL queue with thread-safe read/write
  - Result TTL pruning (default 5 min)
  - Spontaneous event log (capped at 200 entries)
  - \push_command()\ sync helper that the bot uses to dispatch
    a command and block-wait for the phone's reply

- **\	ools/termux_bridge.py\ (19 KB)** ó Phone-side daemon:
  - Single-file Python, **stdlib only** (no FastAPI/pip on phone)
  - Polls Orca \/pending\ every N seconds (configurable)
  - 15 subcommands via Termux:API: battery, wifi, location,
    notify, toast, vibrate, speak, torch, share, clipboard,
    uptime, storage, wake, ping, run
  - Allow-list enforced on phone (defence in depth)
  - Auto-reconnect with exponential backoff
  - \doctor\ subcommand to check termux-api installation
  - \exec\ subcommand to test subcommands locally

- **\skills/termux_skill.py\ (12 KB)** ó Telegram command surface:
  - 18 subcommands: battery, wifi, location, notify, toast,
    vibrate, speak, torch, share, clipboard, uptime, storage,
    wake, ping, run, status, setup, help
  - \cmd_termux(args, chat_id)\ entry point
  - Markdown formatting with 3800-char truncation
  - Friendly error messages with hints
  - **Arabic/Egyptian synonym map** (\"»ÿ«—Ì…\" -> \"battery\",
    \"ﬂ‘«›\" -> \"torch\", etc.) for natural-language routing

- **\	elegram_bot/bot.py\** ó wired \/termux\ (and alias \/phone\):
  - \CommandHandler(\"termux\", self.cmd_termux)\
  - Added to \BotCommand\ list (Telegram menu)
  - Added to \SKILL_CATALOG\
  - \/start\ help text mentions the bridge

- **\skills/intent_skill.py\** ó added 14 new patterns for
  /termux (English + Egyptian), mapped via \_args_subcommand\
  helper that strips trigger verbs (\"check my\", \"⁄«Ì“ «⁄—›\")
  and returns the rest

- **\core/skills_data/termux_bridge.md\** ó design doc with
  architecture, transport choice rationale, subcommand catalogue,
  error model, security model, latency budget

### Live verification

End-to-end test (all 7 steps passed in ~1.3s):
1. Health check (no auth) ? 200 OK
2. Phone polls, queue empty ? []
3. Bot posts /command ? id=817f94adde47
4. Phone polls, gets the command
5. Phone posts /result ? ok=True
6. Bot fetches /result/{id} ? 87% battery, DISCHARGING
7. Phone posts /event (health) ? listable

### Test counts

- 61 new tests across 3 files:
  - \	ests/test_termux_server.py\ (19 tests)
  - \	ests/test_termux_bridge.py\ (16 tests, in-process HTTP)
  - \	ests/test_termux_skill.py\ (26 tests, mocked server)
- 5 new intent tests for /termux NL patterns
- **Total: 475 passed, 5 skipped** (up from 409)

### Lessons learned

1. **HTTP polling wins for NAT bypass.** WebSocket / MQTT / SSH
   tunnel all need an external server or port forwarding. HTTP
   polling is the only thing that Just Works through any WiFi/cell
   network with zero infrastructure.
2. **Bearer token auth is the right fit.** Both sides are
   short-lived and trusted; we don't need OAuth or mTLS. A single
   env var is enough.
3. **JSONL queue > SQLite > Redis.** File-based queue survives
   bot restarts, is human-inspectable (\jq -c . data/termux_queue.jsonl\),
   adds zero new dependencies.
4. **Lazy import of FastAPI in the skill.** The bot doesn't
   pull in FastAPI at startup ó only when /termux is first
   called. Saves ~80ms on cold start and avoids breaking the
   bot if the bridge is not configured.
5. **Defence-in-depth on the allow-list.** Both the bot AND
   the phone validate subcommands. The phone is the source of
   truth ó the bot's check is just for nicer error messages.
6. **Mocked HTTP with \http.server.HTTPServer\.** Testing the
   daemon's poll loop is easy: spin up a BaseHTTPRequestHandler
   on 127.0.0.1, run the bridge in a thread for 0.5s, then
   assert the server received the expected requests.
7. **Synonym map for NL->command routing.** Arabic users say
   \"»ÿ«—Ì…\" but the English subcommand is \attery\". A 30-line
   dict bridges the gap. Add more entries as new phrasings emerge.
8. **Don't break \/status\ for general \"Õ«·…\" queries.** The
   new termux pattern required the phone suffix (\"«·„Ê»«Ì·\" /
   \" ·Ì›Ê‰Ì\") ó without it, \"«ÌÂ Õ«·… «·”Ì—›—ø\" would be
   misclassified as /termux.

---

## 2026-08-03 ó One-shot Windows installer (setup/)

The user asked to move the Orca Agent from this dev environment
to their laptop (\smoha\: i7-6820HQ, 16 GB RAM, Win 10 Pro
22H2, target \D:\ORCA AGENT\). We built a complete PowerShell
installer that does the full setup in one shot.

### What ships

- \setup/setup.ps1\ (15 KB) - one-shot installer with
  progress reporting, admin check, configurable paths
- \setup/run_bot.ps1\ (3 KB) - the actual bot runner
  (loaded by Task Scheduler; loads .env, activates venv, runs
  the bot, logs to logs\orca.log with rotation)
- \setup/keep_awake.ps1\ (3 KB) - Windows sleep-prevention
  watchdog using SetThreadExecutionState Win32 API
- \setup/health_check.ps1\ (4 KB) - periodic health probe
  (every 5 min via Task Scheduler) with Telegram alerts
- \setup/termux_setup.ps1\ (4 KB) - generates the
  termux_bridge.json for the phone with auto-detected LAN IP
- \setup/uninstall.ps1\ (2 KB) - clean removal
- \setup/README.md\ (6 KB) - quickstart + troubleshooting

### What gets installed (via Task Scheduler)

| Task | Trigger | Purpose |
|------|---------|---------|
| OrcaAgent | At logon | Runs the bot, auto-restart on crash |
| OrcaAgentKeepAwake | At logon | Prevents Windows sleep when bot is up |
| OrcaAgentHealthCheck | Every 5 min | Pings bot + bridge, alerts via Telegram |

### One-liner the user runs on their laptop

\\\powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
iwr -useb https://raw.githubusercontent.com/hermasorca13-stack/Orca-Agent-Unified/master/setup/setup.ps1 | iex
\\\

### Lessons learned (the hard way)

1. **Em-dashes and smart quotes are footguns in PowerShell.**
   When we wrote the script with markdown-flavored em-dashes
   (ó), they got encoded as UTF-8 but the file was re-read
   as Latin-1, producing mojibake (\‚Ä"\). PowerShell 5.1
   sees this as a multi-byte token and refuses to parse the
   file (\The term 'X' is not recognized\).
   Fix: use ASCII hyphens (-) only in PowerShell scripts.
2. **Heredocs with \if/else\ inside break the parser.**
   The C#-style \@\u201c...\u201d@\ heredoc with embedded
   \if () { ... } else { ... }\ confuses PowerShell because
   the curly braces in the interpolation get miscounted.
   Fix: compute values into variables first, then interpolate
   in a simple heredoc. Or use a string array.
3. **Trailing commas in arrays break PS 5.1.**
   \@( 'a', 'b', 'c', )\u00a0 is fine in PS 7 but PS 5.1 says
   \Missing expression after ','\. Always omit the trailing comma.
4. **The \&&\ operator does not exist in PowerShell.**
   Use \;\ (sequential) or \-and\ (boolean).
5. **Single quotes inside double-quoted strings are fine
   in theory but the parser chokes on specific patterns.**
   When in doubt, just rewrite the string without inner quotes.
6. **The .NET Parser API parses more leniently than runtime.**
   \[Parser]::ParseFile(...)\ said the file was clean even when
   \powershell -File ...\ failed at runtime with the same content.
   Always smoke-test the actual run, not just the parse.

### Test results

- All 6 setup scripts: \[Parser]::ParseFile()\ returns 0 errors
- \setup.ps1 -SkipTests -SkipService -SkipKeepAwake -SkipHealth\:
  Step 0 (admin check) runs and aborts gracefully on non-admin
  - **Correct behavior** - the user will run it elevated
- All 475 existing tests still pass
- Mojibake fix in termux_skill.py: 503 -> 476 non-ASCII chars
  (preserved 263 Arabic, removed 27 mojibake sequences)
