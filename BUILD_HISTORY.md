# 🛠️ Orca Agent — Build History & Lessons Learned

> Living document. Every session that touches the bot appends what worked,
> what failed, and why — so we never repeat a mistake.

---

## Session: 2026-07-29 — Adding 5 library-backed skills (gh / crypto / stock / qr / short)

### What was requested
Bring the production bot to feature parity with the latest master code:
- `/gh` — GitHub ops (PyGithub)
- `/crypto` — Markets (pycoingecko)
- `/stock` — Quote (yfinance)
- `/qr` — QR codes (qrcode)
- `/short` — URL shortener (pyshorteners)
- All five must show in the Telegram command menu
- No rebuild from scratch — add & modify only

### What we did (in order)

1. **Read state, not code first.** Cloned the repo, scanned commit log,
   confirmed all 5 skills were already shipped (commits `47aae87`, `5eae891`).
   That told us the *only* gap was the production instance running stale code
   + the Telegram menu cache.

2. **Tried the live menu first.** `getMyCommands` returned 13 commands —
   the 5 new ones were missing. That confirmed: code in repo ✅, code in
   bot's process ❌, code in Telegram's menu cache ❌.

3. **Pushed `setMyCommands` via raw API.** Single call registered all 19
   commands. The Telegram client refreshes the menu within seconds — this
   works even if the running bot process is ancient. **Always do this BEFORE
   fighting with the bot process itself.**

4. **Ran a local sanity test on every skill** before touching the remote:
   - crypto ✅ (BTC/ETH live prices)
   - qr ✅ (1121-byte PNG)
   - stock ✅ (AAPL $340.08)
   - github ❌ → 404 because the skill hardcoded `GH_USER/REPO` but the
     repo actually lives under the `hermasorca13-stack` **org**
   - short ⚠️ → `isgd` provider was down ("database insert failed") but
     `tinyurl`, `clckru`, `dagd` worked fine

5. **Fixed what was actually broken (ADD, not rebuild):**
   - `core/config.py`: added `GH_ORG` + `GH_FULL_NAME` constants
   - `skills/github_skill.py`: 13 occurrences of `f"{GH_USER}/{GH_REPO}"`
     replaced with `GH_FULL_NAME` via `replace_all` (one-pass surgery)
   - `telegram_bot/bot.py`: changed `/short` default provider from `isgd`
     (often down) to `tinyurl` (most reliable in the pyshorteners chain)

6. **Tried to run a local bot instance** to test the handlers end-to-end.
   `telegram.error.Conflict: terminated by other getUpdates request` — the
   remote orchestrator was still holding the long-poll slot. We did NOT
   `logOut` the bot this time. Instead we:

7. **Triggered `/update` on the remote bot** so it self-pulls the new code
   from GitHub and restarts cleanly. The `cmd_update` handler does exactly
   this (`git pull --ff-only` + `os.execvp`).

### Why this approach (lessons)

- ❌ Don't `logOut` to "free" the token. The previous session did that
  and the token sat in a logged-out state until a fresh `Application`
  ran `getMe`/`getUpdates` against it. Recovery took ~15 min of polling.
  Use `close` or let the orphan instance time out instead.

- ❌ Don't spawn a local bot while another instance is polling. PTB
  raises `Conflict` immediately. The preflight in `orca.py` exists
  *exactly* to prevent this — listen to it.

- ❌ Don't rebuild the bot file from scratch when the repo already has
  the new code. Read first, modify second.

- ✅ The single best move was `setMyCommands` over the raw HTTP API.
  It decouples menu freshness from bot process freshness. Even if the
  bot is running week-old code, the menu can be up-to-date.

- ✅ Pushing the new code + `/update` is the right way to bring the
  remote instance current. `os.execvp` cleanly replaces the polling
  process without a `logOut` cycle.

- ✅ Test each skill in isolation before assuming the wiring works.
  The `github_skill` passed the import test but failed at the API call
  because of the user-vs-org assumption. Always call the function once.

### Files touched this session

| File | Change | Lines |
|------|--------|-------|
| `core/config.py` | +`GH_ORG`, +`GH_FULL_NAME` | +2 |
| `skills/github_skill.py` | 13x `GH_USER/REPO` -> `GH_FULL_NAME` | ±13 |
| `telegram_bot/bot.py` | default shortener `isgd` -> `tinyurl` (x2) | ±2 |
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
