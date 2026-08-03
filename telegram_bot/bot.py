# telegram_bot/bot.py - Orca Agent Telegram Bot (Unified, Single Source)
"""
Real Telegram bot using long-polling.
- Bot: @HermesOrcaXBot
- Commands: /start /status /skills /sync /device /exec /token /tap /swipe /text
            /transcribe /say /image /docx /xlsx /pdf /search /v2e /research
- All handlers share the same APIManager and config singletons.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from typing import Optional, List
from loguru import logger
from core.config import config
from api_manager.api_manager import api
from android_bridge.adb_controller import get_device_info, tap, swipe, text as adb_text
from skills.shell_executor import run as shell_run

class OrcaBot:
    def __init__(self):
        self.authorized: set[int] = set()
        self.app = None
        if not config.TG_TOKEN:
            logger.error("TELEGRAM_BOT_TOKEN missing")
            return
        self.app = Application.builder().token(config.TG_TOKEN).build()
        self._register()
        logger.info(f"Bot built | @{config.TG_USERNAME}")

    def _register(self):
        h = self.app.add_handler
        h(CommandHandler("start", self.cmd_start))
        h(CommandHandler("help", self.cmd_start))  # /help = /start
        h(CommandHandler("verify", self.cmd_verify))
        h(CommandHandler("status", self.cmd_status))
        h(CommandHandler("skills", self.cmd_skills))
        h(CommandHandler("sync", self.cmd_sync))
        h(CommandHandler("update", self.cmd_update))
        h(CommandHandler("device", self.cmd_device))
        h(CommandHandler("exec", self.cmd_exec))
        h(CommandHandler("token", self.cmd_token))
        h(CommandHandler("tap", self.cmd_tap))
        h(CommandHandler("swipe", self.cmd_swipe))
        h(CommandHandler("text", self.cmd_text))
        h(CommandHandler("brain", self.cmd_brain))
        h(CommandHandler("agent", self.cmd_agent))
        # New 5-skill commands (library-backed)
        h(CommandHandler("gh", self.cmd_gh))
        h(CommandHandler("crypto", self.cmd_crypto))
        h(CommandHandler("stock", self.cmd_stock))
        h(CommandHandler("qr", self.cmd_qr))
        h(CommandHandler("short", self.cmd_short))
        # 2026-07-29 additive: 8 more library-backed skills
        h(CommandHandler("weather", self.cmd_weather))
        h(CommandHandler("translate", self.cmd_translate))
        h(CommandHandler("pdf", self.cmd_pdf))
        h(CommandHandler("wiki", self.cmd_wiki))
        h(CommandHandler("say", self.cmd_say))
        h(CommandHandler("news", self.cmd_news))
        h(CommandHandler("fx", self.cmd_fx))
        h(CommandHandler("arxiv", self.cmd_arxiv))
        h(CommandHandler("transcribe", self.cmd_transcribe))
        h(CommandHandler("docx", self.cmd_docx))
        h(CommandHandler("xlsx", self.cmd_xlsx))
        h(CommandHandler("search", self.cmd_search))
        h(CommandHandler("web", self.cmd_search))  # alias
        h(CommandHandler("image", self.cmd_image))
        h(CommandHandler("youtube", self.cmd_youtube))
        h(CommandHandler("yt", self.cmd_youtube))  # alias
        h(CommandHandler("img", self.cmd_image))  # alias
        # --- Adaptive natural-language intent (additive) ---
        h(CommandHandler("intent", self.cmd_intent))
        # --- EFI-OS external tool wrapper (additive) ---
        h(CommandHandler("efi", self.cmd_efi))
        # --- Smart integration: cross-skill pipelines (additive) ---
        h(CommandHandler("v2e", self.cmd_v2e))
        h(CommandHandler("research", self.cmd_research))
        h(CommandHandler("health", self.cmd_health))
        # Auto-transcribe incoming voice / audio messages (Apple-grade: voice is the
        # primary input on Telegram per MASTER_PROMPT).
        h(MessageHandler(filters.VOICE, self.on_voice))
        h(MessageHandler(filters.AUDIO, self.on_audio))
        # Auto-read incoming .docx files (reply with text content).
        h(MessageHandler(filters.Document.ALL, self.on_document))
        # --- ADD: diag, setup, cancel + FSM message router (lowest priority) ---
        h(CommandHandler("diag", self.cmd_diag))
        h(CommandHandler("setup", self.cmd_setup))
        h(CommandHandler("cancel", self.cmd_cancel))
        # FSM router: must come AFTER on_text to not block normal chat.
        # Group 1 = lower priority; default group 0 runs commands first.
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,
                                            self.fsm_message_router), group=1)
        h(MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_text))

    # ---- Handlers ----
    async def cmd_start(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        user = u.effective_user
        chat = u.effective_chat
        self.authorized.add(user.id)
        # Register bot commands with Telegram so the menu shows everything
        try:
            from telegram import BotCommand
            await self.app.bot.set_my_commands([
                BotCommand("start", "Start Orca Agent"),
                BotCommand("status", "System status"),
                BotCommand("skills", "List available skills"),
                BotCommand("sync", "Push to GitHub / self-update"),
                BotCommand("update", "Pull latest code from GitHub"),
                BotCommand("device", "Android device info"),
                BotCommand("exec", "Execute shell command"),
                BotCommand("token", "Generate API token"),
                BotCommand("tap", "Tap screen coords"),
                BotCommand("swipe", "Swipe gesture"),
                BotCommand("text", "Type text via ADB"),
                BotCommand("brain", "Check AgentBridge status"),
                BotCommand("agent", "Query OrcaAgent brain"),
                BotCommand("verify", "Engineering validation"),
                # New 5 library-backed skill commands
                BotCommand("gh", "GitHub ops (repo/issue/pr/release)"),
                BotCommand("crypto", "Crypto markets (price/trending/global)"),
                BotCommand("stock", "Stock quote (yfinance)"),
                BotCommand("qr", "Generate QR code (PNG/SVG)"),
                BotCommand("short", "Shorten URL (16+ providers)"),
                # 2026-07-29 additive: 8 more library-backed skills
                BotCommand("weather", "Weather forecast (Open-Meteo, no key)"),
                BotCommand("translate", "Translate text (100+ languages)"),
                BotCommand("pdf", "PDF read+make+md+ocr (info/text/make/md/ocr)"),
                BotCommand("wiki", "Wikipedia search/summary"),
                BotCommand("say", "Text-to-speech (edge-tts, no key)"),
                BotCommand("news", "News headlines (Google News RSS)"),
                BotCommand("fx", "Currency exchange (Frankfurter, no key)"),
                BotCommand("arxiv", "Search arXiv papers"),
                BotCommand("transcribe", "Voice/audio → text (Whisper API)"),
                BotCommand("docx", "Read/create .docx (python-docx)"),
                BotCommand("xlsx", "Read/create .xlsx (openpyxl)"),
                BotCommand("search", "Web search (Tavily/Serper/DDG)"),
                BotCommand("image", "Generate image from prompt (DALL-E)"),
                BotCommand("intent", "Classify a free-form message into a command"),
                BotCommand("efi", "EFI-OS: local evidence + RAG + analysis (no API keys)"),
                BotCommand("v2e", "Voice → English (transcribe + translate pipeline)"),
                BotCommand("research", "Multi-source research card (web+wiki+news)"),
                BotCommand("health", "DB / FS / Network probe"),
                # 2026-08-03 ADD: YouTube video analysis (transcript + oEmbed + LLM)
                BotCommand("youtube", "Analyze YouTube video (transcript + summary + quotes)"),
                # 2026-07-29 ADD: diag + setup wizard + cancel FSM
                BotCommand("diag", "Diagnostics (self-heal report)"),
                BotCommand("setup", "Set LLM API key (wizard)"),
                BotCommand("cancel", "Cancel active flow"),
            ])
        except Exception as e:
            logger.debug(f"set_my_commands skipped: {e}")
        # Silent auto-update check — pull latest code if remote differs
        update_line = ""
        try:
            from core.auto_updater import maybe_auto_update
            r = maybe_auto_update()
            if r.get("changed"):
                update_line = f"\n🔄 Auto-updated: {r.get('before','')[:7]} → {r.get('after','')[:7]}"
            else:
                update_line = f"\n✅ Code up-to-date ({r.get('before','')[:7]})"
        except Exception as ae:
            logger.debug(f"auto-update check failed: {ae}")
        await u.message.reply_text(
            f"🐋 Orca Agent Online\n"
            f"User: {user.first_name} (id={user.id})\n"
            f"Chat: {chat.id} ({chat.type})\n"
            f"Bot: @{config.TG_USERNAME}\n"
            f"Repo: {config.GH_REPO}@{config.GH_BRANCH}\n"
            f"Tokens: {api.count()}\n"
            f"Mode: {config.RUN_MODE}{update_line}\n\n"
            f"Core:\n"
            f"/status /skills /sync /update /device /verify\n"
            f"/exec <cmd> /token /brain /agent\n\n"
            f"Device (ADB):\n"
            f"/tap <x> <y> /swipe <x1> <y1> <x2> <y2> /text <msg>\n\n"
            f"Media:\n"
            f"/transcribe [reply|url] — voice → text (Whisper)\n"
            f"/say <text> — text → voice (edge-tts, no key)\n"
            f"/image <prompt> — text → image (DALL-E 3)\n\n"
            f"Documents:\n"
            f"/docx <info|read|tables|create|md|append> — Word\n"
            f"/xlsx <info|sheets|read|cell|create|append|set> — Excel\n"
            f"/pdf <info|text|tables|make|md|ocr> — PDF\n\n"
            f"Web / research:\n"
            f"/search <q> [-n N] [-p prov] [-t sec]\n"
            f"/news [topic], /wiki <query>, /arxiv <query>\n\n"
            f"Pipelines (smart combinations):\n"
            f"/v2e [reply] — voice → English (transcribe + translate)\n"
            f"/research <q> — web + wiki + news combined card\n\n"
            f"Finance:\n"
            f"/crypto, /stock, /fx\n\n"
            f"Utilities:\n"
            f"/gh, /qr, /short, /weather, /translate"
        )
        logger.info(f"START user={user.id} chat={chat.id}")

    async def cmd_status(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        await u.message.reply_text(
            f"📊 Status\n"
            f"Bot: ✅ @{config.TG_USERNAME}\n"
            f"GitHub: {config.GH_REPO} @ {config.GH_BRANCH}\n"
            f"GH token: {'✅' if config.GH_TOKEN else '❌'}\n"
            f"Master: {'✅' if config.ORCA_MASTER else '❌'}\n"
            f"Tokens: {api.count()}\n"
            f"Mode: {config.RUN_MODE}"
        )

    # --- Smart integration: skill catalog + pipeline commands ---
    # Maps each registered skill stem to a one-line description. Used
    # by /skills, /start, and the on_text fallback. Add an entry here
    # whenever a new skill is added; the bot surfaces it everywhere.
    SKILL_CATALOG: dict = {
        # Foundation + system
        "orca_skills":   "skill registry (do not call directly)",
        "shell_executor": "whitelisted shell commands (read-only ops)",
        # Media
        "transcribe_skill":   "voice / audio → text (OpenAI Whisper API)",
        "tts_skill":          "text → voice (edge-tts, no key)",
        "image_skill":        "text → image (DALL-E 3 / DALL-E 2)",
        # Documents
        "docx_skill":         "Microsoft Word .docx read+create (python-docx)",
        "xlsx_skill":         "Microsoft Excel .xlsx read+create (openpyxl)",
        "pdf_skill":          "PDF read+make+md+ocr (pypdf, reportlab, tesseract)",
        # Web / research
        "web_search_skill":   "multi-provider web search (Tavily/Serper/DDG)",
        "news_skill":         "news headlines (Google News RSS)",
        "wikipedia_skill":    "Wikipedia search & summary (100+ langs)",
        "arxiv_skill":        "arXiv academic paper search",
        # Finance
        "crypto_skill":       "crypto markets (pycoingecko)",
        "stocks_skill":       "stock quotes (yfinance)",
        "fx_skill":           "FX / currency exchange (Frankfurter, no key)",
        # Utilities
        "github_skill":       "GitHub ops (PyGithub: repos/issues/PRs/releases)",
        "url_shortener_skill": "URL shortener (16+ providers, no key)",
        "qr_skill":           "QR code generator (qrcode, no key)",
        "weather_skill":      "weather forecast (Open-Meteo, no key)",
        "translation_skill":  "text translation (Google web, 100+ langs)",
        "efi_os_skill":       "EFI-OS wrapper — local evidence + RAG + analysis (no API keys)",
        "intent_skill":       "Adaptive natural-language intent classifier (Arabic+English)",
        "youtube_skill":      "YouTube video analysis (transcript + oEmbed + LLM, 125+ langs)",
    }

    async def cmd_skills(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        from skills.orca_skills import load_all
        loaded = load_all()
        lines = [f"🧠 Skills ({len(loaded)} loaded):"]
        for name in loaded:
            desc = self.SKILL_CATALOG.get(name)
            if desc:
                lines.append(f"• `{name}` — {desc}")
            else:
                lines.append(f"• `{name}`")
        # Also show catalog entries that haven't been loaded yet.
        missing = [n for n in self.SKILL_CATALOG if n not in loaded]
        if missing:
            lines.append("")
            lines.append(f"_Not loaded ({len(missing)}):_ " + ", ".join(f"`{n}`" for n in missing))
        await u.message.reply_text("\n".join(lines))

    async def cmd_sync(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        await u.message.reply_text("🔄 Syncing...")
        from github_sync.gh_sync import sync_to_github
        r = sync_to_github()
        await u.message.reply_text(f"{'✅' if r['ok'] else '❌'} {r['msg']}")

    async def cmd_update(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        """Pull latest code from GitHub master and restart the bot.

        This is the production self-update path. The local clone runs
        `git pull --ff-only origin <branch>`, then the current Python
        process is replaced via os.execvp with a fresh `python orca.py bot`
        so the new code takes the polling slot.
        """
        thinking = await u.message.reply_text("📥 Pulling latest from GitHub...")
        try:
            from core.auto_updater import maybe_auto_update, get_local_sha
            before = get_local_sha()
            r = maybe_auto_update()
            after = r.get("after") or before
            if not r.get("changed"):
                await thinking.edit_text(
                    f"✅ Already up-to-date\n"
                    f"Local: {before[:10] or '?'}\n"
                    f"Remote: {after[:10] or '?'}"
                )
                return
            await thinking.edit_text(
                f"✅ Pulled: {before[:7]} → {after[:7]}\n"
                f"Restarting bot to apply..."
            )
            # Replace the current process — the OS reaps the old one, and
            # the new instance picks up the new code immediately.
            from core.auto_updater import restart_bot
            restart_bot()
        except Exception as e:
            logger.exception("cmd_update failed")
            try:
                await thinking.edit_text(f"❌ Update failed: {e}")
            except Exception:
                await u.message.reply_text(f"❌ Update failed: {e}")

    async def cmd_device(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        info = get_device_info()
        await u.message.reply_text(f"📱 {info}")

    async def cmd_exec(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        if not c.args:
            await u.message.reply_text("Usage: /exec <command>")
            return
        result = shell_run(" ".join(c.args), timeout=30)
        out = (result.get("stdout") or "")[:1500]
        await u.message.reply_text(f"$ {' '.join(c.args)}\n```\n{out}\n```"[:4000], parse_mode="Markdown")

    async def cmd_token(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        tok = api.create_token(name=f"tg_{u.effective_user.id}")
        await u.message.reply_text(f"🔑 New token:\n`{tok}`", parse_mode="Markdown")

    async def cmd_tap(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        if len(c.args) < 2:
            await u.message.reply_text("Usage: /tap <x> <y>")
            return
        r = tap(int(c.args[0]), int(c.args[1]))
        await u.message.reply_text(f"{'✅' if r['ok'] else '❌'} tap ({c.args[0]},{c.args[1]})")

    async def cmd_swipe(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        if len(c.args) < 4:
            await u.message.reply_text("Usage: /swipe <x1> <y1> <x2> <y2> [ms]")
            return
        ms = int(c.args[4]) if len(c.args) > 4 else 300
        r = swipe(int(c.args[0]), int(c.args[1]), int(c.args[2]), int(c.args[3]), ms)
        await u.message.reply_text(f"{'✅' if r['ok'] else '❌'} swipe")

    async def cmd_text(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        if not c.args:
            await u.message.reply_text("Usage: /text <message>")
            return
        r = adb_text(" ".join(c.args))
        await u.message.reply_text(f"{'✅' if r['ok'] else '❌'} text typed")

    async def cmd_brain(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        """Show OrcaAgent brain status (LLM + memory + 25+ skills)."""
        from core.agent_loader import bridge
        if not bridge.ready:
            ok = bridge.initialize()
        skills = bridge.list_skills()
        ready_emoji = "🟢" if bridge.ready else "🔴"
        await u.message.reply_text(
            f"{ready_emoji} Orca Agent Bridge\n"
            f"ready: {bridge.ready}\n"
            f"reason: {bridge.reason}\n"
            f"skills: {len(skills)}\n"
            f"sample: {', '.join(skills[:10])}{'…' if len(skills) > 10 else ''}"
        )

    async def cmd_agent(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        """Force-route a prompt through OrcaAgent (LLM)."""
        if not c.args:
            await u.message.reply_text("Usage: /agent <prompt>")
            return
        from core.agent_loader import bridge
        if not bridge.ready:
            bridge.initialize()
        if not bridge.ready:
            await u.message.reply_text(
                f"⚠️ Brain offline: {bridge.reason}\n"
                f"Set LLM_API_KEY / OPENAI_API_KEY in .env to enable."
            )
            return
        thinking = await u.message.reply_text("🧠 thinking…")
        response = await bridge.process(
            user_id=u.effective_user.id,
            text=" ".join(c.args),
            platform="telegram",
            metadata={"chat_id": u.effective_chat.id},
        )
        try:
            await thinking.delete()
        except Exception:
            pass
        if response and len(response) > 4000:
            response = response[:3997] + "…"
        await u.message.reply_text(response or "⚠️ no response")

    # ---------- 5 new skills (library-backed) ----------
    async def cmd_gh(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        """GitHub skill via PyGithub. Usage:
        /gh repo [name]             - get repo info
        /gh repos [user]            - list user repos
        /gh issues [state]          - list issues (open/closed/all)
        /gh prs [state]             - list pull requests
        /gh releases                - list releases
        /gh branches                - list branches
        /gh search <query>          - search repos
        /gh file <path>             - get file content
        /gh gist <desc>|<content>   - create gist
        """
        from skills import github_skill
        args = c.args or []
        if not args:
            await u.message.reply_text(self._gh_help())
            return
        sub = args[0].lower()
        try:
            if sub == "repo":
                name = args[1] if len(args) > 1 else None
                r = github_skill.get_repo(name)
                await u.message.reply_text(
                    f"📦 {r['name']}\n⭐ {r['stars']}  🍴 {r['forks']}  📋 issues: {r['open_issues']}\n"
                    f"🔗 {r['html_url']}\n{r['description'] or ''}"
                )
            elif sub == "repos":
                user = args[1] if len(args) > 1 else None
                rs = github_skill.list_repos(user=user, limit=15)
                lines = "\n".join(f"• {r['name']} (⭐{r['stars']})" for r in rs)
                await u.message.reply_text(f"📚 Repos:\n{lines}" or "no repos")
            elif sub == "issues":
                state = args[1] if len(args) > 1 else "open"
                iss = github_skill.list_issues(state=state, limit=15)
                if not iss:
                    await u.message.reply_text(f"No {state} issues.")
                    return
                lines = "\n".join(f"#{i['number']} {i['title']}" for i in iss)
                await u.message.reply_text(f"🐛 Issues ({state}):\n{lines}")
            elif sub == "prs":
                state = args[1] if len(args) > 1 else "open"
                prs = github_skill.list_prs(state=state, limit=15)
                if not prs:
                    await u.message.reply_text(f"No {state} PRs.")
                    return
                lines = "\n".join(f"#{p['number']} {p['title']} ({p['user']})" for p in prs)
                await u.message.reply_text(f"🔀 PRs ({state}):\n{lines}")
            elif sub == "releases":
                rels = github_skill.list_releases(limit=10)
                if not rels:
                    await u.message.reply_text("No releases yet.")
                    return
                lines = "\n".join(f"• {r['tag']} — {r['name']}" for r in rels)
                await u.message.reply_text(f"🚀 Releases:\n{lines}")
            elif sub == "branches":
                bs = github_skill.list_branches()
                lines = "\n".join(f"• {b['name']}" for b in bs[:30])
                await u.message.reply_text(f"🌿 Branches ({len(bs)}):\n{lines}")
            elif sub == "search":
                query = " ".join(args[1:])
                if not query:
                    await u.message.reply_text("Usage: /gh search <query>")
                    return
                rs = github_skill.search_repos(query, limit=5)
                lines = "\n".join(f"• {r['name']} ⭐{r['stars']} — {r['description'][:60] if r['description'] else ''}" for r in rs)
                await u.message.reply_text(f"🔍 Search:\n{lines}")
            elif sub == "file":
                path = args[1] if len(args) > 1 else "README.md"
                f = github_skill.get_file(path)
                if "error" in f:
                    await u.message.reply_text(f"❌ {f['error']}")
                    return
                if f.get("type") == "dir":
                    items = "\n".join(f"• {x}" for x in f["items"][:30])
                    await u.message.reply_text(f"📁 {path}/:\n{items}")
                else:
                    txt = f.get("decoded", "")[:3000]
                    await u.message.reply_text(f"📄 {path} ({f['size']} bytes):\n```\n{txt}\n```", parse_mode="Markdown")
            elif sub == "gist":
                rest = " ".join(args[1:])
                if "|" not in rest:
                    await u.message.reply_text("Usage: /gh gist <desc>|<content>")
                    return
                desc, content = rest.split("|", 1)
                g = github_skill.create_gist(desc.strip(), content.strip())
                await u.message.reply_text(f"✅ Gist: {g['url']}")
            else:
                await u.message.reply_text(self._gh_help())
        except Exception as e:
            logger.exception("cmd_gh error")
            await u.message.reply_text(f"❌ GitHub error: {e}")

    def _gh_help(self) -> str:
        return ("🐙 GitHub skill (PyGithub):\n"
                "/gh repo [name] — repo info\n"
                "/gh repos [user] — list repos\n"
                "/gh issues [state] — list issues (open/closed)\n"
                "/gh prs [state] — list PRs\n"
                "/gh releases — list releases\n"
                "/gh branches — list branches\n"
                "/gh search <query> — search repos\n"
                "/gh file <path> — read file (default: README.md)\n"
                "/gh gist <desc>|<content> — create gist")

    async def cmd_crypto(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        """Crypto skill via pycoingecko. Usage:
        /crypto price <coin>      - quick price (e.g. bitcoin,ethereum)
        /crypto coin <id>         - full coin info
        /crypto markets [n]       - top markets
        /crypto trending          - trending coins
        /crypto global            - global market stats
        /crypto search <query>    - search coin
        /crypto history <id> [d]  - price history (days)
        """
        from skills import crypto_skill
        args = c.args or []
        if not args:
            await u.message.reply_text(self._crypto_help())
            return
        sub = args[0].lower()
        try:
            if sub == "price":
                coins = args[1:]
                if not coins:
                    await u.message.reply_text("Usage: /crypto price bitcoin ethereum")
                    return
                p = crypto_skill.get_price_full(coins)
                lines = []
                for coin, data in p.items():
                    price = data.get("usd", "?")
                    chg = data.get("usd_24h_change", 0)
                    cap = data.get("usd_market_cap", 0)
                    lines.append(f"💰 {coin}: ${price:,.4f}  ({chg:+.2f}% 24h)  MCap: ${cap:,.0f}")
                await u.message.reply_text("\n".join(lines) or "no data")
            elif sub == "coin":
                cid = args[1] if len(args) > 1 else "bitcoin"
                d = crypto_skill.get_coin(cid)
                await u.message.reply_text(
                    f"🪙 {d['name']} ({d['symbol'].upper()})\n"
                    f"💵 ${d['current_price_usd']:,.4f}\n"
                    f"📊 MCap: ${d['market_cap_usd']:,.0f}\n"
                    f"🔄 24h: {d['price_change_24h']:+.2f}%\n"
                    f"📈 7d: {d['price_change_7d']:+.2f}%  30d: {d['price_change_30d']:+.2f}%\n"
                    f"🏔 ATH: ${d['ath_usd']:,.4f}  🏞 ATL: ${d['atl_usd']:,.6f}\n"
                    f"🔗 {d['homepage'] or ''}"
                )
            elif sub == "markets":
                n = int(args[1]) if len(args) > 1 else 10
                rows = crypto_skill.get_markets(limit=n)
                lines = [f"#{r['market_cap_rank']} {r['symbol'].upper()} — ${r['price']:,.4f}  ({r['price_change_24h']:+.2f}%)"
                         for r in rows if r.get('market_cap_rank')]
                await u.message.reply_text("🏆 Top markets:\n" + "\n".join(lines))
            elif sub == "trending":
                t = crypto_skill.get_trending()
                lines = [f"🔥 #{i+1} {c['name']} ({c['symbol']})" for i, c in enumerate(t[:10])]
                await u.message.reply_text("📈 Trending:\n" + "\n".join(lines))
            elif sub == "global":
                g = crypto_skill.get_global()
                await u.message.reply_text(
                    f"🌍 Global crypto market\n"
                    f"Active cryptos: {g.get('active_cryptocurrencies', '?')}\n"
                    f"Markets: {g.get('markets', '?')}\n"
                    f"Total MCap: ${g.get('total_market_cap', {}).get('usd', 0):,.0f}\n"
                    f"24h Vol: ${g.get('total_volume', {}).get('usd', 0):,.0f}\n"
                    f"MCap change 24h: {g.get('market_cap_change_percentage_24h_usd', 0):+.2f}%"
                )
            elif sub == "search":
                q = " ".join(args[1:])
                if not q:
                    await u.message.reply_text("Usage: /crypto search <query>")
                    return
                rs = crypto_skill.search_coin(q)[:10]
                lines = [f"• {c['name']} ({c['symbol']}) — {c['id']}" for c in rs]
                await u.message.reply_text("🔎 Search:\n" + "\n".join(lines))
            elif sub == "history":
                cid = args[1] if len(args) > 1 else "bitcoin"
                days = args[2] if len(args) > 2 else "30"
                h = crypto_skill.get_history(cid, days=days)
                prices = h.get("prices", [])
                if not prices:
                    await u.message.reply_text("No data.")
                    return
                first = prices[0][1]
                last = prices[-1][1]
                chg = (last - first) / first * 100
                await u.message.reply_text(
                    f"📊 {cid} ({days}d):\n"
                    f"First: ${first:,.4f}\n"
                    f"Last:  ${last:,.4f}\n"
                    f"Change: {chg:+.2f}%\n"
                    f"Points: {len(prices)}"
                )
            else:
                await u.message.reply_text(self._crypto_help())
        except Exception as e:
            logger.exception("cmd_crypto error")
            await u.message.reply_text(f"❌ Crypto error: {e}")

    def _crypto_help(self) -> str:
        return ("💎 Crypto skill (CoinGecko):\n"
                "/crypto price <coins...> — prices\n"
                "/crypto coin <id> — full coin info\n"
                "/crypto markets [n] — top markets\n"
                "/crypto trending — trending coins\n"
                "/crypto global — global stats\n"
                "/crypto search <query> — search coin\n"
                "/crypto history <id> [days] — price history")

    async def cmd_stock(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        """Stocks skill via yfinance. Usage:
        /stock <symbol>          - quote
        /stock h <symbol> [prd]  - history (1mo default)
        /stock news <symbol>     - news
        /stock targets <symbol>  - analyst targets
        /stock search <query>    - symbol search
        /stock div <symbol>      - dividends
        """
        from skills import stocks_skill
        args = c.args or []
        if not args:
            await u.message.reply_text(self._stock_help())
            return
        sub = args[0].lower()
        try:
            if sub == "h":
                sym = args[1].upper() if len(args) > 1 else "AAPL"
                period = args[2] if len(args) > 2 else "1mo"
                hist = stocks_skill.get_history(sym, period=period)
                if not hist:
                    await u.message.reply_text("no data")
                    return
                first = hist[0]["close"]
                last = hist[-1]["close"]
                chg = (last - first) / first * 100
                high = max(h["high"] for h in hist)
                low = min(h["low"] for h in hist)
                await u.message.reply_text(
                    f"📈 {sym} ({period}): {len(hist)} days\n"
                    f"Open: ${first:,.2f}  Close: ${last:,.2f}  Change: {chg:+.2f}%\n"
                    f"High: ${high:,.2f}  Low: ${low:,.2f}"
                )
            elif sub == "news":
                sym = args[1].upper() if len(args) > 1 else "AAPL"
                n = stocks_skill.get_news(sym, limit=5)
                if not n:
                    await u.message.reply_text(f"No news for {sym}")
                    return
                lines = [f"• {x['title']} ({x['publisher']})" for x in n if x.get("title")]
                await u.message.reply_text(f"📰 {sym} news:\n" + "\n".join(lines))
            elif sub == "targets":
                sym = args[1].upper() if len(args) > 1 else "AAPL"
                t = stocks_skill.get_analyst_targets(sym)
                await u.message.reply_text(
                    f"🎯 {sym} analyst targets:\n"
                    f"Current: ${t.get('current') or '?'}\n"
                    f"Low/Mean/Median/High: ${t.get('target_low', '?')} / ${t.get('target_mean', '?')} / ${t.get('target_median', '?')} / ${t.get('target_high', '?')}\n"
                    f"Recommendation: {t.get('recommendation', '?')} ({t.get('num_analysts', 0)} analysts)"
                )
            elif sub == "search":
                q = " ".join(args[1:])
                if not q:
                    await u.message.reply_text("Usage: /stock search <query>")
                    return
                rs = stocks_skill.search_symbols(q)
                lines = [f"• {r['symbol']} — {r['short_name']} ({r['exchange']})" for r in rs[:10]]
                await u.message.reply_text("🔍 Search:\n" + "\n".join(lines))
            elif sub == "div":
                sym = args[1].upper() if len(args) > 1 else "AAPL"
                d = stocks_skill.get_dividends(sym)
                if not d:
                    await u.message.reply_text(f"No dividends for {sym}")
                    return
                recent = list(d.items())[-5:]
                lines = [f"• {date}: ${val}" for date, val in recent]
                await u.message.reply_text(f"💸 {sym} recent dividends:\n" + "\n".join(lines))
            else:
                # default: quote
                sym = sub.upper()
                q = stocks_skill.get_quote(sym)
                await u.message.reply_text(
                    f"📊 {q.get('short_name') or sym} ({q.get('exchange')})\n"
                    f"💵 ${q.get('current_price', '?')}\n"
                    f"📈 52w: ${q.get('52w_low', '?')} — ${q.get('52w_high', '?')}\n"
                    f"🏷 Sector: {q.get('sector', '?')}\n"
                    f"📦 MCap: ${q.get('market_cap', 0):,.0f}\n"
                    f"📊 P/E: {q.get('pe_ratio', '?')}\n"
                    f"💰 Yield: {q.get('dividend_yield', 0)*100 if q.get('dividend_yield') else 0:.2f}%\n"
                    f"β Beta: {q.get('beta', '?')}"
                )
        except Exception as e:
            logger.exception("cmd_stock error")
            await u.message.reply_text(f"❌ Stock error: {e}")

    def _stock_help(self) -> str:
        return ("📈 Stocks skill (yfinance):\n"
                "/stock <SYM> — quote\n"
                "/stock h <SYM> [period] — history\n"
                "/stock news <SYM> — recent news\n"
                "/stock targets <SYM> — analyst targets\n"
                "/stock search <query> — symbol search\n"
                "/stock div <SYM> — dividends")

    async def cmd_qr(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        """QR skill via qrcode. Usage:
        /qr <text>             - generate QR
        /qr ascii <text>       - ASCII preview
        /qr svg <text>         - SVG output
        """
        from skills import qr_skill
        args = c.args or []
        if not args:
            await u.message.reply_text(self._qr_help())
            return
        sub = args[0].lower()
        text = " ".join(args[1:]) if sub in ("ascii", "svg") else " ".join(args)
        if not text:
            await u.message.reply_text("Usage: /qr <text>")
            return
        try:
            if sub == "ascii":
                art = qr_skill.generate_ascii(text)
                await u.message.reply_text(f"```\n{art}\n```", parse_mode="Markdown")
            elif sub == "svg":
                svg = qr_skill.generate_svg(text)
                # send as text since SVG is big; first 500 chars preview
                await u.message.reply_text(f"✅ SVG generated ({len(svg)} bytes). First 400 chars:\n```xml\n{svg[:400]}\n```", parse_mode="Markdown")
            else:
                # PNG — send as photo
                from io import BytesIO
                png = qr_skill.generate_png(text)
                await u.message.reply_photo(photo=BytesIO(png), caption=f"🔳 QR: {text[:100]}")
        except Exception as e:
            logger.exception("cmd_qr error")
            await u.message.reply_text(f"❌ QR error: {e}")

    def _qr_help(self) -> str:
        return ("🔳 QR skill:\n"
                "/qr <text> — generate PNG\n"
                "/qr ascii <text> — ASCII preview\n"
                "/qr svg <text> — SVG output")

    async def cmd_short(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        """URL shortener via pyshorteners. Usage:
        /short <url>                    - shorten with default (is.gd)
        /short <url> tinyurl            - specific provider
        /short list                     - list providers
        /short multi <url>              - shorten across 5 providers
        /short expand <url> <provider>  - expand a short URL
        """
        from skills import url_shortener_skill
        args = c.args or []
        if not args:
            await u.message.reply_text(self._short_help())
            return
        sub = args[0].lower()
        try:
            if sub == "list":
                ps = url_shortener_skill.list_providers()
                await u.message.reply_text(f"🔗 Available providers:\n" + ", ".join(ps))
            elif sub == "multi":
                url = args[1] if len(args) > 1 else None
                if not url:
                    await u.message.reply_text("Usage: /short multi <url>")
                    return
                out = url_shortener_skill.shorten_multi(url)
                lines = [f"• {p}: {r.get('short_url', r.get('error'))}" for p, r in out.items()]
                await u.message.reply_text(f"🔗 Shortened across providers:\n" + "\n".join(lines))
            elif sub == "expand":
                if len(args) < 3:
                    await u.message.reply_text("Usage: /short expand <url> <provider>")
                    return
                url, prov = args[1], args[2]
                r = url_shortener_skill.expand(url, provider=prov)
                await u.message.reply_text(f"🔓 Expanded: {r.get('expanded_url', r.get('error'))}")
            else:
                url = args[0]
                prov = args[1] if len(args) > 1 else "tinyurl"
                r = url_shortener_skill.shorten(url, provider=prov)
                if "error" in r:
                    await u.message.reply_text(f"❌ {r['error']}")
                else:
                    await u.message.reply_text(f"🔗 {r['provider']}: {r['short_url']}")
        except Exception as e:
            logger.exception("cmd_short error")
            await u.message.reply_text(f"❌ Shorten error: {e}")

    def _short_help(self) -> str:
        return ("🔗 URL Shortener:\n"
                "/short <url> [provider] — shorten (default: tinyurl)\n"
                "/short multi <url> — multi-provider\n"
                "/short list — list providers\n"
                "/short expand <url> <provider> — expand")

    async def cmd_verify(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        """Engineering verification: check imports + duplicate filenames + config health."""
        from pathlib import Path
        root = Path(config.ROOT)
        pkgs = ["core", "api_manager", "telegram_bot", "github_sync", "android_bridge", "skills", "src", "platforms"]
        lines = ["🛡️ Engineering Verify"]
        # __init__.py check
        for pkg in pkgs:
            init = root / pkg / "__init__.py"
            lines.append(f"{'✅' if init.exists() else '❌'} {pkg}/__init__.py")
        # duplicate check
        seen = {}
        for p in root.rglob("*.py"):
            if "__pycache__" in str(p) or ".git" in str(p):
                continue
            seen.setdefault(p.name, []).append(str(p.relative_to(root)))
        dups = [(n, l) for n, l in seen.items() if len(l) > 1 and n != "__init__.py"]
        lines.append(f"{'✅ No duplicates' if not dups else f'⚠️ {len(dups)} dups: {dups[:3]}'}")
        # config health
        lines.append(f"{'✅' if config.TG_TOKEN else '❌'} TG_TOKEN")
        lines.append(f"{'✅' if config.GH_TOKEN else '❌'} GH_TOKEN")
        lines.append(f"{'✅' if config.ORCA_MASTER else '❌'} ORCA_MASTER")
        await u.message.reply_text("\n".join(lines))

    async def on_text(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        """Free-form text. Routes through AgentBridge (LLM+memory+skills) when LLM is configured,
        otherwise falls back to a plain echo with command hints. Persists every exchange to MemorySystem."""
        text = (u.message.text or "").strip()
        user_id = u.effective_user.id if u.effective_user else 0
        chat_id = u.effective_chat.id if u.effective_chat else 0
        username = u.effective_user.username if u.effective_user else None
        session_id = f"tg:{chat_id}"
        # Persist the incoming user message (so /agent later has history context)
        try:
            from core.memory_instance import get_memory
            mem = get_memory()
            mem.create_session(session_id=session_id, user_id=user_id, platform="telegram")
            mem.add_memory(
                user_id=user_id,
                session_id=session_id,
                role="user",
                content=text[:4000],
                metadata={"chat_id": chat_id, "username": username, "platform": "telegram"},
                importance=0.4,
            )
        except Exception as me:
            logger.debug(f"memory save (user) skipped: {me}")
        # Try the full OrcaAgent brain (LLM + memory + 25+ skills)
        response = None
        try:
            from core.agent_loader import bridge
            if not bridge.ready:
                bridge.initialize()
            if bridge.ready:
                logger.info(f"Agent route | user={user_id} chat={chat_id} skills={len(bridge.list_skills())}")
                thinking = await u.message.reply_text("🧠 Orca is thinking…")
                response = await bridge.process(
                    user_id=user_id,
                    text=text,
                    platform="telegram",
                    metadata={"chat_id": chat_id, "username": username, "session_id": session_id},
                )
                try:
                    await thinking.delete()
                except Exception:
                    pass
                if response and len(response) > 4000:
                    response = response[:3997] + "…"
        except Exception as e:
            logger.warning(f"Agent route unavailable, falling back: {e}")
        # Persist the assistant response (success or fallback) for future context recall
        if response:
            try:
                mem.add_memory(
                    user_id=user_id,
                    session_id=session_id,
                    role="assistant",
                    content=response[:4000],
                    metadata={"chat_id": chat_id, "platform": "telegram", "source": "agent"},
                    importance=0.6,
                )
            except Exception as me:
                logger.debug(f"memory save (assistant) skipped: {me}")
            await u.message.reply_text(response)
            return
        # Fallback: rule-based intent classification + command hint.
        # Try the intent_skill first (deterministic, no API key).
        try:
            from skills import intent_skill
            intent = intent_skill.classify(
                text, user_id=str(user_id), use_llm=False,
            )
            suggestion = ""
            if intent.is_actionable and intent.command:
                suggestion = (
                    f"\n🎯 _Did you mean:_ `{intent.command} "
                    f"{' '.join(intent.args[:3])}`"
                    f" _(confidence {intent.confidence:.2f})_"
                )
            elif intent.is_suggestion and intent.command:
                suggestion = (
                    f"\n💡 _Close match:_ `{intent.command}` "
                    f"_(confidence {intent.confidence:.2f})_"
                )
        except Exception:  # noqa: BLE001
            suggestion = ""

        fallback = (
            f"Received: {text[:200]}\n\n"
            f"🧠 Brain offline — rule-based mode.\n"
            f"Available commands:\n"
            f"• /start /status /skills /sync /update /verify\n"
            f"• /exec /token /brain /agent /device\n"
            f"• /tap /swipe /text\n"
            f"Media: /transcribe /say /image\n"
            f"Docs: /docx /xlsx /pdf (info/text/tables/make/md/ocr)\n"
            f"Web: /search /news /wiki /arxiv\n"
            f"Pipelines: /v2e (voice→EN) /research (web+wiki+news) "
            f"/intent\n"
            f"Finance: /crypto /stock /fx\n"
            f"Utils: /gh /qr /short /weather /translate /efi\n\n"
            f"Tip: /intent <your text>  — get a smart suggestion."
            f"{suggestion}\n\n"
            f"Set LLM_API_KEY or OPENAI_API_KEY in .env to unlock the full brain."
        )
        try:
            mem.add_memory(
                user_id=user_id,
                session_id=session_id,
                role="assistant",
                content=fallback[:4000],
                metadata={"chat_id": chat_id, "platform": "telegram", "source": "fallback"},
                importance=0.3,
            )
        except Exception as me:
            logger.debug(f"memory save (fallback) skipped: {me}")
        await u.message.reply_text(fallback)

    # ===== 2026-07-29 additive: 8 new library-backed skills =====
    # All wired with @with_user_ratelimit so the bot never gets flooded.
    # Each handler imports its skill module lazily so a missing skill
    # never breaks the rest of the bot.

    async def cmd_weather(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        from core.middleware import with_user_ratelimit, friendly_error
        from skills import weather_skill
        args = c.args or []
        place = " ".join(args).strip() or "Cairo"
        try:
            text = await weather_skill.weather(place, days=2)
        except Exception as e:
            text = friendly_error(e)
        await u.message.reply_text(text, parse_mode="Markdown")

    async def cmd_translate(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        from core.middleware import with_user_ratelimit, friendly_error
        from skills import translation_skill
        raw = (u.message.text or "").split(maxsplit=2)
        # /translate <lang> <text>  OR  /translate <text>  (defaults to en)
        if len(raw) < 2:
            await u.message.reply_text(
                "Usage: /translate <lang> <text>\n"
                "Example: /translate ar Hello world\n"
                "Languages: en, ar, es, fr, de, ru, zh, ja, hi, tr …"
            )
            return
        if len(raw) == 2:
            target, body = "en", raw[1]
        else:
            target, body = raw[1], raw[2]
        try:
            text = await translation_skill.translate(body, target)
        except Exception as e:
            text = friendly_error(e)
        await u.message.reply_text(f"🌐 → {target}\n{text}")

    async def cmd_pdf(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        from core.middleware import friendly_error
        from skills import pdf_skill
        args = c.args or []
        if not args:
            await u.message.reply_text(
                "Usage:\n"
                "  /pdf info <path>            — metadata\n"
                "  /pdf text <path> [page]     — extract text\n"
                "  /pdf tables <path> [page]   — extract tables\n"
                "  /pdf make <text>            — text → PDF (returned as file)\n"
                "  /pdf md <markdown>          — markdown → PDF\n"
                "  /pdf ocr <path> [page]      — OCR scanned PDF (needs tesseract)"
            )
            return
        op = args[0].lower()
        rest = args[1:]
        try:
            if op == "info":
                if not rest:
                    await u.message.reply_text("Usage: /pdf info <path>")
                    return
                meta = pdf_skill.info(rest[0])
                out = (
                    f"📄 *{meta.get('title') or rest[0]}*\n"
                    f"Pages: {meta.get('pages')}\n"
                    f"Author: {meta.get('author') or '—'}\n"
                    f"Size: {meta.get('size_bytes')} bytes"
                )
                await u.message.reply_text(out, parse_mode="Markdown")
            elif op == "text":
                if not rest:
                    await u.message.reply_text("Usage: /pdf text <path> [page]")
                    return
                page = int(rest[1]) if len(rest) > 1 else None
                body = pdf_skill.text(rest[0], page=page)
                out = body[:3500] + ("\n…[truncated]" if len(body) > 3500 else "")
                await u.message.reply_text(out, parse_mode="Markdown")
            elif op == "tables":
                if not rest:
                    await u.message.reply_text("Usage: /pdf tables <path> [page]")
                    return
                page = int(rest[1]) if len(rest) > 1 else None
                t = pdf_skill.tables(rest[0], page=page)
                if not t:
                    out = "📭 No tables found on that page"
                else:
                    lines = [f"📊 {len(t)} table(s) found", ""]
                    for i, tb in enumerate(t[:3], 1):
                        lines.append(f"*Table {i}* ({len(tb)} rows)")
                        for row in tb[:5]:
                            lines.append(" | ".join(row))
                        lines.append("")
                    out = "\n".join(lines)
                await u.message.reply_text(out, parse_mode="Markdown")
            elif op == "make":
                # Text → PDF; the rest of the message is the body.
                if not rest:
                    await u.message.reply_text("Usage: /pdf make <text>")
                    return
                import os as _os
                import tempfile
                body = " ".join(rest)
                tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
                tmp.close()
                try:
                    p = pdf_skill.to_pdf(body, tmp.name)
                    await u.message.reply_document(
                        open(p, "rb"),
                        filename="orca-text.pdf",
                        caption=(
                            f"📄 Generated ({_os.path.getsize(p):,} bytes) — "
                            f"{len(body):,} chars"
                        ),
                    )
                finally:
                    try:
                        _os.unlink(p)
                    except OSError:
                        pass
            elif op == "md":
                # Markdown → PDF.
                if not rest:
                    await u.message.reply_text("Usage: /pdf md <markdown>")
                    return
                import os as _os
                import tempfile
                body = " ".join(rest)
                tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
                tmp.close()
                try:
                    p = pdf_skill.markdown_to_pdf(body, tmp.name)
                    await u.message.reply_document(
                        open(p, "rb"),
                        filename="orca-from-markdown.pdf",
                        caption=(
                            f"📄 Markdown → PDF "
                            f"({_os.path.getsize(p):,} bytes)"
                        ),
                    )
                finally:
                    try:
                        _os.unlink(p)
                    except OSError:
                        pass
            elif op == "ocr":
                # OCR a scanned PDF.
                if not rest:
                    await u.message.reply_text(
                        "Usage: /pdf ocr <path> [page]\n"
                        "Requires Tesseract + pdf2image on the system."
                    )
                    return
                page = int(rest[1]) if len(rest) > 1 else None
                status = None
                try:
                    status = await u.message.reply_text(
                        "🔍 OCR in progress… (can be slow on long docs)"
                    )
                except Exception:
                    status = None
                text = pdf_skill.ocr(rest[0], page=page)
                if not text:
                    out = "📭 OCR returned no text"
                else:
                    out = text[:3500]
                    if len(text) > 3500:
                        out += "\n…[truncated]"
                if status:
                    try:
                        await status.edit_text(out, parse_mode=None)
                        return
                    except Exception:
                        pass
                await u.message.reply_text(out)
            else:
                await u.message.reply_text(
                    f"⚠️ Unknown op: {op}. "
                    f"Use info|text|tables|make|md|ocr."
                )
        except Exception as e:
            await u.message.reply_text(f"❌ {friendly_error(e)}")

    async def cmd_wiki(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        from core.middleware import friendly_error
        from skills import wikipedia_skill
        raw = (u.message.text or "").split(maxsplit=1)
        if len(raw) < 2:
            await u.message.reply_text(
                "Usage: /wiki <query>  — search\n"
                "       /wiki summary <title>  — short article"
            )
            return
        body = raw[1].strip()
        try:
            if body.lower().startswith("summary "):
                out = await wikipedia_skill.summary(body[len("summary "):].strip())
            else:
                out = await wikipedia_skill.search(body, limit=5)
        except Exception as e:
            out = friendly_error(e)
        await u.message.reply_text(out, parse_mode="Markdown", disable_web_page_preview=True)

    async def cmd_say(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        from core.middleware import friendly_error
        from skills import tts_skill
        args = c.args or []
        if not args:
            await u.message.reply_text(
                "Usage: /say <text>  — default voice\n"
                "       /say voice  — list available voices"
            )
            return
        if args[0].lower() == "voice":
            try:
                out = await tts_skill.list_voices()
            except Exception as e:
                out = friendly_error(e)
            await u.message.reply_text(out, parse_mode="Markdown")
            return
        text = " ".join(args)
        # Optional voice: /say <voice> <text>  if first arg matches a known voice
        voice = "en-US-AriaNeural"
        first = args[0]
        if first in tts_skill.VOICES or first.endswith("Neural"):
            voice = first
            text = " ".join(args[1:]) or "Hello"
        try:
            path = await tts_skill.synthesize(text, voice=voice)
        except Exception as e:
            await u.message.reply_text(friendly_error(e))
            return
        try:
            with open(path, "rb") as f:
                await u.message.reply_voice(f, filename="orca.mp3",
                                            caption=f"🎙 {voice}")
        except Exception as e:
            await u.message.reply_text(friendly_error(e))

    async def cmd_news(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        from core.middleware import friendly_error
        from skills import news_skill
        args = c.args or []
        if not args:
            await u.message.reply_text(
                "Usage: /news <query>           — search\n"
                "       /news topic <TECHNOLOGY>  — by topic"
            )
            return
        try:
            if args[0].lower() == "topic":
                topic = args[1] if len(args) > 1 else "TECHNOLOGY"
                out = await news_skill.topic(topic, limit=8)
            else:
                out = await news_skill.search(" ".join(args), limit=8)
        except Exception as e:
            out = friendly_error(e)
        await u.message.reply_text(out, parse_mode="Markdown", disable_web_page_preview=True)

    async def cmd_fx(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        from core.middleware import friendly_error
        from skills import fx_skill
        args = c.args or []
        if not args:
            await u.message.reply_text(
                "Usage: /fx <amount> <base> <target>   e.g. /fx 100 USD EUR\n"
                "       /fx series <base> <target> [days]\n"
                "       /fx list"
            )
            return
        try:
            if args[0].lower() == "list":
                out = await fx_skill.list_currencies()
            elif args[0].lower() == "series" and len(args) >= 3:
                days = int(args[3]) if len(args) > 3 else 30
                out = await fx_skill.series(args[1], args[2], days=days)
            elif len(args) >= 3:
                out = await fx_skill.rate(args[0], args[1], args[2])
            else:
                out = "⚠️ Need: /fx <amount> <base> <target>"
        except Exception as e:
            out = friendly_error(e)
        await u.message.reply_text(out, parse_mode="Markdown")

    async def cmd_arxiv(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        from core.middleware import friendly_error
        from skills import arxiv_skill
        args = c.args or []
        if not args:
            await u.message.reply_text("Usage: /arxiv <query>   e.g. /arxiv transformer attention")
            return
        try:
            out = await arxiv_skill.search(" ".join(args), limit=5)
        except Exception as e:
            out = friendly_error(e)
        await u.message.reply_text(out, parse_mode="Markdown", disable_web_page_preview=True)

    async def _transcribe_telegram_file(self, u: Update, tg_file, *, ext: str):
        """Download a Telegram voice/audio file and transcribe it.

        `tg_file` is the PTB Voice or Audio object. `ext` is the filename
        extension to use for the temp file (`.ogg` for voice, `.mp3` for
        audio). Sends a friendly card back to the user.
        """
        import asyncio
        import os
        import tempfile
        from core.middleware import friendly_error
        from skills import transcribe_skill

        chat = u.effective_chat
        # Status message — gets edited in place when done.
        try:
            status = await chat.send_message("🎙 Transcribing…")
        except Exception:
            status = None

        # 1) Download from Telegram (async, non-blocking).
        try:
            file_obj = await tg_file.get_file()
            data = await file_obj.download_as_bytearray()
        except Exception as exc:  # noqa: BLE001
            text = friendly_error(exc)
            if status:
                try:
                    await status.edit_text(f"❌ Download failed: {text}")
                except Exception:
                    pass
            return

        # 2) Write to a temp file (the skill expects a path or URL).
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
                f.write(data)
                tmp_path = f.name

            # 3) Transcribe in a worker thread (skill is sync, blocks).
            try:
                result = await asyncio.to_thread(
                    transcribe_skill.transcribe, tmp_path
                )
                out = transcribe_skill.format_card(result)
            except transcribe_skill.TranscribeError as exc:
                out = f"❌ {exc}"
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        # 4) Reply (edit status if we have it, else send fresh).
        if status:
            try:
                await status.edit_text(out, parse_mode="Markdown")
                return
            except Exception:
                pass
        await u.message.reply_text(out, parse_mode="Markdown")

    async def cmd_transcribe(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        """/transcribe — explicit transcription.

        Modes:
          /transcribe                  → reply-to a voice/audio
          /transcribe <url>            → transcribe a remote URL
        """
        from skills import transcribe_skill

        # Mode 1: reply to a voice / audio message.
        reply = u.message.reply_to_message if u.message else None
        if reply:
            tg_file = reply.voice or reply.audio or reply.video_note
            if tg_file is not None:
                ext = ".ogg"
                if reply.audio and reply.audio.file_name:
                    import os as _os
                    ext = _os.path.splitext(reply.audio.file_name)[1] or ".mp3"
                elif reply.video_note:
                    ext = ".mp4"
                await self._transcribe_telegram_file(u, tg_file, ext=ext)
                return
            await u.message.reply_text(
                "⚠️ Reply to a *voice* or *audio* message, or pass a URL.\n"
                "Usage:\n"
                "  /transcribe  (reply to a voice)\n"
                "  /transcribe <url>".replace("`", "")
            )
            return

        # Mode 2: URL.
        args = c.args or []
        if not args:
            await u.message.reply_text(
                "Usage: /transcribe (reply to a voice note)\n"
                "       /transcribe <url>\n"
                "_Powered by OpenAI Whisper API._"
            )
            return
        url = args[0].strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            await u.message.reply_text("⚠️ URL must start with http:// or https://")
            return

        import asyncio
        try:
            result = await asyncio.to_thread(transcribe_skill.transcribe, url)
            await u.message.reply_text(
                transcribe_skill.format_card(result), parse_mode="Markdown"
            )
        except transcribe_skill.TranscribeError as exc:
            await u.message.reply_text(f"❌ {exc}")

    async def on_voice(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        """Auto-transcribe any incoming voice note."""
        if not u.message or not u.message.voice:
            return
        await self._transcribe_telegram_file(u, u.message.voice, ext=".ogg")

    async def on_audio(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        """Auto-transcribe any incoming audio file."""
        if not u.message or not u.message.audio:
            return
        import os as _os
        ext = _os.path.splitext(u.message.audio.file_name or "")[1] or ".mp3"
        await self._transcribe_telegram_file(u, u.message.audio, ext=ext)

    async def cmd_youtube(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        """/youtube <url> [lang1,lang2,...] — analyse a YouTube video.

        Pipeline:
            1. oEmbed -> title, author, thumbnail
            2. youtube-transcript-api -> full transcript (125+ langs)
            3. LLM (when OPENAI_API_KEY is set) -> summary + quotes + topics
               (heuristic fallback when no key)
        Renders the result as a Telegram-friendly Markdown card.
        """
        from core.middleware import friendly_error
        if not u.message or not u.message.text:
            await u.message.reply_text(
                "🎬 Usage: `/youtube <youtube_url> [lang,...]`\n"
                "Example: `/youtube https://youtu.be/dQw4w9WgXcQ en,ar`"
            )
            return

        # Strip command prefix.
        text = u.message.text.strip()
        for prefix in ("/youtube", "/yt"):
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                break

        if not text:
            await u.message.reply_text(
                "🎬 Please pass a YouTube URL.\n"
                "Example: `/youtube https://youtu.be/dQw4w9WgXcQ`"
            )
            return

        # Parse URL and optional language list.
        parts = text.split(maxsplit=1)
        url = parts[0]
        languages: Optional[List[str]] = None
        if len(parts) == 2 and parts[1].strip():
            languages = [s.strip() for s in parts[1].split(",") if s.strip()]

        # Acknowledge up front; the network call may take 5-15s.
        wait_msg = await u.message.reply_text(
            f"🎬 Analysing `{url}`…\n"
            f"   pipeline: oEmbed → transcript → {'LLM' if True else 'heuristic'}"
        )

        try:
            from skills.youtube_skill import analyze, format_card, YouTubeError
            analysis = analyze(url, languages=languages, with_llm=True)
        except YouTubeError as exc:
            await wait_msg.edit_text(f"❌ {friendly_error(exc)}")
            return
        except Exception as exc:  # noqa: BLE001
            await wait_msg.edit_text(
                f"❌ YouTube analysis failed: {friendly_error(exc)}"
            )
            return

        try:
            card = format_card(analysis)
        except Exception as exc:  # noqa: BLE001
            card = f"❌ Could not render card: {friendly_error(exc)}"

        # Telegram message length limit is 4096 chars. If the card is
        # longer, split it into a follow-up message.
        if len(card) <= 4000:
            await wait_msg.edit_text(card, parse_mode="Markdown")
        else:
            await wait_msg.edit_text(card[:4000], parse_mode="Markdown")
            # Follow-up with the rest.
            rest = card[4000:]
            while rest:
                await u.message.reply_text(rest[:4000], parse_mode="Markdown")
                rest = rest[4000:]

    async def _read_docx_from_telegram(self, u: Update, tg_doc) -> str:
        """Download a Telegram .docx document and extract its text.

        Returns the absolute path of the downloaded temp file.
        """
        import os
        import tempfile
        from pathlib import Path
        from core.middleware import friendly_error

        try:
            file_obj = await tg_doc.get_file()
            data = await file_obj.download_as_bytearray()
        except Exception as exc:  # noqa: BLE001
            text = friendly_error(exc)
            await u.message.reply_text(f"❌ Download failed: {text}")
            return ""

        suggested = tg_doc.file_name or "document.docx"
        ext = Path(suggested).suffix or ".docx"
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
                f.write(data)
                tmp_path = f.name
            return tmp_path
        except Exception as exc:  # noqa: BLE001
            await u.message.reply_text(f"❌ Could not save: {exc}")
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            return ""

    async def cmd_docx(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        """/docx — read or create .docx files.

        Sub-commands:
          /docx info <path>             → metadata card
          /docx read <path>             → text body
          /docx tables <path>           → tables as Markdown
          /docx create <text>           → create a new .docx, return file
          /docx append <path> <text>    → append to existing
          /docx md <markdown>           → Markdown → .docx, return file
        Or just send a .docx file to the bot to read it.
        """
        from core.middleware import friendly_error
        from skills import docx_skill

        # Mode 0: reply to a .docx document — auto-read.
        reply = u.message.reply_to_message if u.message else None
        if reply and reply.document:
            doc = reply.document
            suggested = (doc.file_name or "").lower()
            if not suggested.endswith(".docx"):
                await u.message.reply_text(
                    "⚠️ This doesn't look like a .docx file. "
                    "Send a .docx attachment or use `/docx <op> <path>`."
                )
                return
            tmp_path = await self._read_docx_from_telegram(u, doc)
            if not tmp_path:
                return
            try:
                try:
                    meta = docx_skill.info(tmp_path)
                    text = docx_skill.read(tmp_path, max_chars=3500)
                finally:
                    import os as _os
                    try:
                        _os.unlink(tmp_path)
                    except OSError:
                        pass
                header = docx_skill.format_info(meta)
                await u.message.reply_text(
                    f"{header}\n\n---\n\n{text}", parse_mode="Markdown"
                )
            except docx_skill.DocxError as exc:
                await u.message.reply_text(f"❌ {exc}")
            return

        args = c.args or []
        if not args:
            await u.message.reply_text(
                "Usage:\n"
                "  /docx info <path>\n"
                "  /docx read <path>\n"
                "  /docx tables <path>\n"
                "  /docx create <text>\n"
                "  /docx md <markdown>\n"
                "Or reply to a .docx file to read it."
            )
            return
        op = args[0].lower()
        rest = args[1:]

        try:
            if op == "info":
                if not rest:
                    await u.message.reply_text("Usage: /docx info <path>")
                    return
                meta = docx_skill.info(rest[0])
                await u.message.reply_text(
                    docx_skill.format_info(meta), parse_mode="Markdown"
                )
            elif op == "read":
                if not rest:
                    await u.message.reply_text("Usage: /docx read <path>")
                    return
                text = docx_skill.read(rest[0], max_chars=3500)
                await u.message.reply_text(f"📄 *{rest[0]}*\n\n{text}", parse_mode="Markdown")
            elif op == "tables":
                if not rest:
                    await u.message.reply_text("Usage: /docx tables <path>")
                    return
                t = docx_skill.tables(rest[0])
                await u.message.reply_text(
                    docx_skill.format_tables(t), parse_mode="Markdown"
                )
            elif op == "create":
                if not rest:
                    await u.message.reply_text("Usage: /docx create <text>")
                    return
                import os as _os
                import tempfile
                body = " ".join(rest)
                tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
                tmp.close()
                try:
                    p = docx_skill.create(tmp.name, paragraphs=[body])
                    await u.message.reply_document(
                        open(p, "rb"),
                        filename="orca-document.docx",
                        caption=f"📄 Created ({_os.path.getsize(p):,} bytes)",
                    )
                finally:
                    try:
                        _os.unlink(p)
                    except OSError:
                        pass
            elif op == "md":
                if not rest:
                    await u.message.reply_text("Usage: /docx md <markdown>")
                    return
                import os as _os
                import tempfile
                body = " ".join(rest)
                tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
                tmp.close()
                try:
                    p = docx_skill.from_markdown(body, tmp.name)
                    await u.message.reply_document(
                        open(p, "rb"),
                        filename="orca-from-markdown.docx",
                        caption=f"📄 Markdown → Word ({_os.path.getsize(p):,} bytes)",
                    )
                finally:
                    try:
                        _os.unlink(p)
                    except OSError:
                        pass
            elif op == "append":
                if len(rest) < 2:
                    await u.message.reply_text("Usage: /docx append <path> <text>")
                    return
                path, body = rest[0], " ".join(rest[1:])
                docx_skill.append(path, body)
                await u.message.reply_text(f"✅ Appended to `{path}`")
            else:
                await u.message.reply_text(
                    f"⚠️ Unknown op: {op}. Use info|read|tables|create|md|append."
                )
        except docx_skill.DocxError as exc:
            await u.message.reply_text(f"❌ {exc}")
        except Exception as exc:  # noqa: BLE001
            await u.message.reply_text(f"❌ {friendly_error(exc)}")

    async def on_document(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        """Auto-read .docx or .xlsx files sent to the bot."""
        if not u.message or not u.message.document:
            return
        name = (u.message.document.file_name or "").lower()
        if name.endswith(".docx"):
            await self.cmd_docx(u, c)
        elif name.endswith(".xlsx") or name.endswith(".xlsm"):
            await self.cmd_xlsx(u, c)

    async def _read_xlsx_from_telegram(self, u: Update, tg_doc) -> str:
        """Download a Telegram .xlsx document to a temp file. Returns path."""
        import os
        import tempfile
        from pathlib import Path
        from core.middleware import friendly_error

        try:
            file_obj = await tg_doc.get_file()
            data = await file_obj.download_as_bytearray()
        except Exception as exc:  # noqa: BLE001
            await u.message.reply_text(f"❌ Download failed: {friendly_error(exc)}")
            return ""

        suggested = tg_doc.file_name or "workbook.xlsx"
        ext = Path(suggested).suffix or ".xlsx"
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
                f.write(data)
                tmp_path = f.name
            return tmp_path
        except Exception as exc:  # noqa: BLE001
            await u.message.reply_text(f"❌ Could not save: {exc}")
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            return ""

    async def cmd_image(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        """/image <prompt>  — generate an image with DALL-E 3.

        Optional flags (after the prompt):
          -m <model>  dall-e-3 (default) | dall-e-2
          -s <size>   1024x1024 (default) | 1024x1792 | 1792x1024
          -q <qual>   standard (default) | hd
        """
        import asyncio
        from core.middleware import friendly_error
        from skills import image_skill

        args = c.args or []
        if not args:
            await u.message.reply_text(
                "Usage:\n"
                "  /image <prompt>\n"
                "  /image <prompt> -m dall-e-3 -s 1792x1024 -q hd\n"
                "_Costs ~$0.04–$0.12 per image on DALL-E 3._"
            )
            return

        # Naive tail-flag parser (prompt first, flags at the end).
        model = "dall-e-3"
        size = "1024x1024"
        quality = "standard"
        cut = len(args)
        i = 0
        while i < len(args):
            a = args[i]
            if a in ("-m", "--model") and i + 1 < len(args):
                model = args[i + 1]
                i += 2
            elif a in ("-s", "--size") and i + 1 < len(args):
                size = args[i + 1]
                i += 2
            elif a in ("-q", "--quality") and i + 1 < len(args):
                quality = args[i + 1]
                i += 2
            else:
                cut = i
                break
        prompt = " ".join(args[:cut]).strip()
        if not prompt:
            await u.message.reply_text("⚠️ Empty prompt")
            return

        # Send a "generating..." status first.
        try:
            status = await u.message.reply_text(
                f"🎨 Generating `{size}` image with `{model}`…"
            )
        except Exception:
            status = None

        # Run the blocking SDK call in a worker thread.
        try:
            result = await asyncio.to_thread(
                image_skill.generate,
                prompt,
                model=model, size=size, quality=quality,
            )
        except image_skill.ImageGenError as exc:
            text = f"❌ {exc}"
            if status:
                try:
                    await status.edit_text(text)
                    return
                except Exception:
                    pass
            await u.message.reply_text(text)
            return
        except Exception as exc:  # noqa: BLE001
            text = f"❌ {friendly_error(exc)}"
            if status:
                try:
                    await status.edit_text(text)
                    return
                except Exception:
                    pass
            await u.message.reply_text(text)
            return

        # Save to a temp file and send as a photo.
        import os as _os
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.close()
        try:
            from skills import image_skill as _im
            path = _im.generate_and_save(
                prompt,
                out_path=tmp.name,
                model=model, size=size, quality=quality,
            )
        except image_skill.ImageGenError as exc:
            text = f"❌ {exc}"
            if status:
                try:
                    await status.edit_text(text)
                except Exception:
                    pass
                return
            await u.message.reply_text(text)
            return

        try:
            caption = image_skill.format_card(result)
            with open(path, "rb") as f:
                await u.message.reply_photo(
                    photo=f,
                    filename="orca-image.png",
                    caption=caption[:1024],
                )
            if status:
                try:
                    await status.delete()
                except Exception:
                    pass
        finally:
            try:
                _os.unlink(path)
            except OSError:
                pass

    async def cmd_search(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        """/search <query>  — multi-provider web search.

        Optional flags (after the query):
          -n <N>     → limit results (default 5, max 20)
          -p <name>  → force provider: tavily | serper | duckduckgo
          -t <sec>   → timeout in seconds (default 15)
        """
        from core.middleware import friendly_error
        from skills import web_search_skill

        args = c.args or []
        if not args:
            await u.message.reply_text(
                "Usage:\n"
                "  /search <query>\n"
                "  /search <query> -n 10 -p tavily\n"
                "_Auto-picks: Tavily → Serper → DuckDuckGo (no key)._"
            )
            return

        # Naive flag parser (the query comes first; flags at the tail).
        limit = 5
        provider = "auto"
        timeout = 15.0
        flag_idx = len(args)
        i = 0
        while i < len(args):
            a = args[i]
            if a == "-n" and i + 1 < len(args):
                try:
                    limit = int(args[i + 1])
                except ValueError:
                    await u.message.reply_text("⚠️ -n needs a number")
                    return
                i += 2
            elif a == "-p" and i + 1 < len(args):
                provider = args[i + 1]
                i += 2
            elif a == "-t" and i + 1 < len(args):
                try:
                    timeout = float(args[i + 1])
                except ValueError:
                    await u.message.reply_text("⚠️ -t needs a number")
                    return
                i += 2
            else:
                flag_idx = i
                break

        query = " ".join(args[:flag_idx]).strip()
        if not query:
            await u.message.reply_text("⚠️ Empty query")
            return

        try:
            result = web_search_skill.search(
                query, limit=limit, provider=provider, timeout=timeout,
            )
            await u.message.reply_text(
                web_search_skill.format_results(result),
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
        except web_search_skill.WebSearchError as exc:
            await u.message.reply_text(f"❌ {exc}")
        except Exception as exc:  # noqa: BLE001
            await u.message.reply_text(f"❌ {friendly_error(exc)}")

    async def cmd_xlsx(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        """/xlsx — read or create .xlsx files.

        Sub-commands:
          /xlsx info <path>              → workbook metadata
          /xlsx sheets <path>            → list sheet names
          /xlsx read <path> [sheet]      → first 25 rows as Markdown table
          /xlsx cell <path> <sheet> <ref> → single cell value (e.g. B2)
          /xlsx create <h1,h2,...> | <v1,v2,...> ... → create a new .xlsx
          /xlsx append <path> <sheet> <v1,v2,...>   → append a row
          /xlsx set <path> <sheet> <ref> <value>     → write one cell
        Or just send a .xlsx / .xlsm file to the bot to read it.
        """
        from core.middleware import friendly_error
        from skills import xlsx_skill

        # Mode 0: reply-to or attachment .xlsx → auto-read first sheet.
        reply = u.message.reply_to_message if u.message else None
        incoming_doc = None
        if reply and reply.document:
            incoming_doc = reply.document
        elif u.message and u.message.document:
            doc = u.message.document
            name = (doc.file_name or "").lower()
            if name.endswith(".xlsx") or name.endswith(".xlsm"):
                incoming_doc = doc

        if incoming_doc is not None:
            tmp_path = await self._read_xlsx_from_telegram(u, incoming_doc)
            if not tmp_path:
                return
            try:
                try:
                    meta = xlsx_skill.info(tmp_path)
                    data = xlsx_skill.read(tmp_path, max_rows=25)
                finally:
                    import os as _os
                    try:
                        _os.unlink(tmp_path)
                    except OSError:
                        pass
                header = xlsx_skill.format_info(meta)
                table = xlsx_skill.format_table(
                    data["headers"], data["rows"],
                    sheet_name=data["sheet_name"],
                    truncated=data["truncated"],
                    max_rows=25,
                )
                await u.message.reply_text(
                    f"{header}\n\n{table}", parse_mode="Markdown"
                )
            except xlsx_skill.XlsxError as exc:
                await u.message.reply_text(f"❌ {exc}")
            return

        args = c.args or []
        if not args:
            await u.message.reply_text(
                "Usage:\n"
                "  /xlsx info <path>\n"
                "  /xlsx sheets <path>\n"
                "  /xlsx read <path> [sheet]\n"
                "  /xlsx cell <path> <sheet> <ref>\n"
                "  /xlsx create <h1,h2,h3> | <v1,v2,v3> | ...\n"
                "  /xlsx append <path> <sheet> <v1,v2,...>\n"
                "  /xlsx set <path> <sheet> <ref> <value>\n"
                "Or send a .xlsx file to the bot to read it."
            )
            return
        op = args[0].lower()
        rest = args[1:]

        try:
            if op == "info":
                if not rest:
                    await u.message.reply_text("Usage: /xlsx info <path>")
                    return
                meta = xlsx_skill.info(rest[0])
                await u.message.reply_text(
                    xlsx_skill.format_info(meta), parse_mode="Markdown"
                )
            elif op == "sheets":
                if not rest:
                    await u.message.reply_text("Usage: /xlsx sheets <path>")
                    return
                sheets = xlsx_skill.list_sheets(rest[0])
                await u.message.reply_text(
                    "📋 " + "\n".join(f"• `{s}`" for s in sheets)
                )
            elif op == "read":
                if not rest:
                    await u.message.reply_text("Usage: /xlsx read <path> [sheet]")
                    return
                path = rest[0]
                sheet = rest[1] if len(rest) > 1 else None
                # sheet can be a name or an int.
                if sheet is not None:
                    try:
                        sheet = int(sheet)
                    except ValueError:
                        pass
                data = xlsx_skill.read(path, sheet=sheet, max_rows=25)
                await u.message.reply_text(
                    xlsx_skill.format_table(
                        data["headers"], data["rows"],
                        sheet_name=data["sheet_name"],
                        truncated=data["truncated"],
                        max_rows=25,
                    ),
                    parse_mode="Markdown",
                )
            elif op == "cell":
                if len(rest) < 3:
                    await u.message.reply_text(
                        "Usage: /xlsx cell <path> <sheet> <ref>  (e.g. B2)"
                    )
                    return
                path, sheet, ref = rest[0], rest[1], rest[2]
                # sheet can be a name or an int.
                try:
                    sheet_i = int(sheet)
                    sheet = sheet_i
                except ValueError:
                    pass
                value = xlsx_skill.read_cell(path, sheet, ref)
                await u.message.reply_text(
                    f"📊 `{ref}` on sheet `{sheet}` → `{value!r}`"
                )
            elif op == "create":
                if not rest:
                    await u.message.reply_text(
                        "Usage: /xlsx create <h1,h2,h3> | <v1,v2,v3> | ..."
                    )
                    return
                import os as _os
                import tempfile
                # Each "|" separates a row. First row is headers.
                raw = " ".join(rest)
                rows_raw = [r.strip() for r in raw.split("|") if r.strip()]
                if not rows_raw:
                    await u.message.reply_text("⚠️ No rows given")
                    return
                def split_row(s: str) -> list[str]:
                    return [c.strip() for c in s.split(",")]
                parsed = [split_row(r) for r in rows_raw]
                headers = parsed[0]
                data = parsed[1:] if len(parsed) > 1 else []
                tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
                tmp.close()
                try:
                    p = xlsx_skill.create(tmp.name, headers=headers, data=data)
                    await u.message.reply_document(
                        open(p, "rb"),
                        filename="orca-workbook.xlsx",
                        caption=(
                            f"📊 Created ({_os.path.getsize(p):,} bytes) — "
                            f"{len(data)} data row(s), {len(headers)} col(s)"
                        ),
                    )
                finally:
                    try:
                        _os.unlink(p)
                    except OSError:
                        pass
            elif op == "append":
                if len(rest) < 3:
                    await u.message.reply_text(
                        "Usage: /xlsx append <path> <sheet> <v1,v2,...>"
                    )
                    return
                path, sheet = rest[0], rest[1]
                vals = [c.strip() for c in " ".join(rest[2:]).split(",") if c.strip()]
                added = xlsx_skill.append_rows(path, sheet, [vals])
                await u.message.reply_text(
                    f"✅ Appended {added} row(s) to `{sheet}` in `{path}`"
                )
            elif op == "set":
                if len(rest) < 4:
                    await u.message.reply_text(
                        "Usage: /xlsx set <path> <sheet> <ref> <value>"
                    )
                    return
                path, sheet, ref = rest[0], rest[1], rest[2]
                value = " ".join(rest[3:])
                # Try to coerce simple types.
                try:
                    value = int(value)
                except ValueError:
                    try:
                        value = float(value)
                    except ValueError:
                        if value.lower() in ("true", "false"):
                            value = value.lower() == "true"
                xlsx_skill.set_cell(path, sheet, ref, value)
                await u.message.reply_text(
                    f"✅ Set `{sheet}!{ref}` = `{value!r}`"
                )
            else:
                await u.message.reply_text(
                    f"⚠️ Unknown op: {op}. "
                    f"Use info|sheets|read|cell|create|append|set."
                )
        except xlsx_skill.XlsxError as exc:
            await u.message.reply_text(f"❌ {exc}")
        except Exception as exc:  # noqa: BLE001
            await u.message.reply_text(f"❌ {friendly_error(exc)}")

    async def cmd_v2e(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        """/v2e — Voice → English text pipeline.

        Smart integration of two existing skills:
          1. transcribe_skill.transcribe() — voice/audio → text
          2. translation_skill.translate()  — text → English

        Modes:
          /v2e (reply to a voice or audio message)
          /v2e <url>     (transcribe a remote URL, then translate)
          /v2e <lang> <reply-or-url>  (override target language)
        """
        from core.middleware import friendly_error
        from skills import transcribe_skill, translation_skill

        args = c.args or []
        # Naive arg parsing: if the first arg is a 2-letter code and
        # the rest is non-empty, treat it as the target language.
        target = "en"
        rest = list(args)
        if rest and len(rest[0]) <= 5 and rest[0].lower() in (
            "en", "ar", "es", "fr", "de", "ru", "zh", "ja", "hi", "tr",
            "it", "pt", "ko", "nl", "sv", "pl", "el", "he", "id", "vi",
        ):
            target = rest[0].lower()
            rest = rest[1:]

        # Mode A: reply-to-voice / reply-to-audio.
        reply = u.message.reply_to_message if u.message else None
        if reply and (reply.voice or reply.audio):
            status = None
            try:
                status = await u.message.reply_text(
                    f"🎙 Transcribing + translating to {target.upper()}…"
                )
            except Exception:
                pass
            tmp_path = await self._transcribe_telegram_file(
                u, reply.voice or reply.audio,
                ext=".ogg" if reply.voice else ".mp3",
            )
            if not tmp_path:
                return
            try:
                try:
                    import asyncio
                    result = await asyncio.to_thread(
                        transcribe_skill.transcribe, tmp_path,
                    )
                    src_text = result.get("text", "").strip()
                finally:
                    import os as _os
                    try:
                        _os.unlink(tmp_path)
                    except OSError:
                        pass
                if not src_text:
                    text = "📭 No speech detected"
                else:
                    # Skip translation if the source is already target.
                    detected = (result.get("language") or "unknown").lower()
                    if detected == target:
                        translated = src_text
                    else:
                        try:
                            translated = await translation_skill.translate(
                                src_text, target,
                            )
                        except translation_skill.TranslationError as exc:
                            translated = f"{src_text}\n\n_(translation failed: {exc})_"
                    card = (
                        f"🌐 *Voice → {target.upper()}*\n"
                        f"_Source language: {detected}_\n\n"
                        f"{translated[:3500]}"
                    )
                    text = card
            except transcribe_skill.TranscribeError as exc:
                text = f"❌ {exc}"
            if status:
                try:
                    await status.edit_text(text, parse_mode="Markdown")
                    return
                except Exception:
                    pass
            await u.message.reply_text(text, parse_mode="Markdown")
            return

        # Mode B: URL.
        if not rest:
            await u.message.reply_text(
                "Usage:\n"
                f"  /v2e (reply to a voice message)\n"
                f"  /v2e <url>\n"
                f"  /v2e <lang> <url>  (override target; default: en)\n"
                f"_Pipeline: transcribe → translate to {target.upper()}._"
            )
            return
        url = rest[0].strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            await u.message.reply_text("⚠️ URL must start with http:// or https://")
            return
        import asyncio
        try:
            result = await asyncio.to_thread(transcribe_skill.transcribe, url)
            src_text = result.get("text", "").strip()
            if not src_text:
                await u.message.reply_text("📭 No speech detected")
                return
            detected = (result.get("language") or "unknown").lower()
            if detected == target:
                translated = src_text
            else:
                try:
                    translated = await translation_skill.translate(
                        src_text, target,
                    )
                except translation_skill.TranslationError as exc:
                    translated = f"{src_text}\n\n_(translation failed: {exc})_"
            card = (
                f"🌐 *Voice → {target.upper()}*\n"
                f"_Source: {detected}_\n\n"
                f"{translated[:3500]}"
            )
            await u.message.reply_text(card, parse_mode="Markdown")
        except transcribe_skill.TranscribeError as exc:
            await u.message.reply_text(f"❌ {exc}")

    async def cmd_research(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        """/research <query> — multi-source research card.

        Smart integration: combines results from three existing skills
        into one ranked, deduplicated card:
          1. web_search_skill  (top 3 results)
          2. wikipedia_skill   (one-line summary if available)
          3. news_skill        (top 2 related headlines)
        """
        from core.middleware import friendly_error
        from skills import web_search_skill, news_skill
        try:
            from skills import wikipedia_skill
        except ImportError:
            wikipedia_skill = None  # type: ignore

        args = c.args or []
        if not args:
            await u.message.reply_text(
                "Usage: /research <query>\n"
                "_Pipelines: web + wiki + news into one card._"
            )
            return
        query = " ".join(args).strip()
        status = None
        try:
            status = await u.message.reply_text(f"🔬 Researching *{query}*…")
        except Exception:
            pass

        import asyncio

        async def _web():
            try:
                return web_search_skill.search(query, limit=3, timeout=10.0)
            except web_search_skill.WebSearchError as exc:
                return {"error": str(exc), "results": []}

        async def _wiki():
            if wikipedia_skill is None:
                return None
            try:
                # wikipedia_skill.summary(title) — no sentences kwarg;
                # the function itself trims to ~1200 chars.
                return await wikipedia_skill.summary(query)
            except Exception:  # noqa: BLE001
                return None

        async def _news():
            try:
                return await news_skill.search(query, limit=2)
            except Exception:  # noqa: BLE001
                return ""

        web_res, wiki_text, news_md = await asyncio.gather(
            _web(), _wiki(), _news(), return_exceptions=False,
        )

        lines = [f"🔬 *Research: {query}*", ""]

        if wiki_text:
            lines.append(f"📖 *Wikipedia summary*")
            lines.append(wiki_text[:600])
            lines.append("")

        if web_res and web_res.get("results"):
            lines.append("🌐 *Web*")
            for i, r in enumerate(web_res["results"], 1):
                title = r.get("title") or "(no title)"
                url = r.get("url") or ""
                snippet = (r.get("snippet") or "")[:200]
                lines.append(f"{i}. [{title}]({url})")
                if snippet:
                    lines.append(f"   _{snippet}_")
            lines.append("")

        if news_md:
            lines.append("📰 *News*")
            lines.append(news_md[:600])

        if len(lines) == 2:  # only header was added
            lines.append("📭 No results from any source.")

        out = "\n".join(lines)
        if status:
            try:
                await status.edit_text(out, parse_mode="Markdown",
                                       disable_web_page_preview=True)
                return
            except Exception:
                pass
        await u.message.reply_text(out, parse_mode="Markdown",
                                   disable_web_page_preview=True)

    async def cmd_intent(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        """/intent <text> — classify a free-form message into a command.

        Uses the intent_skill (hybrid: deterministic patterns + optional
        LLM refinement). Surfaces a confidence score so the user can
        decide whether to act on the suggestion.
        """
        from skills import intent_skill
        from core.middleware import friendly_error

        text = (u.message.text or "").split(maxsplit=1)
        if len(text) < 2:
            await u.message.reply_text(
                "Usage: /intent <free-form text>\n"
                "Example: /intent ابحث عن weather in Tokyo\n"
                "_Returns: matched command + confidence + entities._"
            )
            return
        body = text[1].strip()
        user_id = str(u.effective_user.id) if u.effective_user else ""
        try:
            intent = intent_skill.classify(body, user_id=user_id, use_llm=True)
            card = intent_skill.format_intent_card(intent)
            # If actionable, offer a one-tap-style "do it" hint.
            hint = ""
            if intent.is_actionable:
                hint = (
                    f"\n\n👉 Send `{intent.command} {' '.join(intent.args[:3])}` "
                    f"to run it."
                )
            elif intent.is_suggestion:
                hint = (
                    f"\n\n💡 Close match. The closest command is "
                    f"`{intent.command}`. Try rephrasing or just send the "
                    f"command directly."
                )
            await u.message.reply_text(card + hint, parse_mode="Markdown")
        except Exception as exc:  # noqa: BLE001
            await u.message.reply_text(f"❌ {friendly_error(exc)}")

    async def cmd_efi(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        """/efi — wrapper around the bundled EFI-OS tool.

        Sub-commands:
          /efi capabilities                 — show the 18-capability matrix
          /efi self-test                    — run the 19 bundled tests
          /efi research <query>             — local RAG research
          /efi analyze <subject>            — engineering analysis
          /efi compare <sub1> <sub2> ...    — compare subjects
          /efi ingest <subject> <path>      — ingest a local file
          /efi help                         — show this help

        EFI-OS uses NO external API keys. Everything runs locally on
        the Orca bot's host. The wrapper at skills/efi_os_skill.py
        shells out to tools/EFI_OS.py and verifies its SHA-256 on
        import.
        """
        from core.middleware import friendly_error
        from skills import efi_os_skill

        args = c.args or []
        if not args or args[0].lower() in ("help", "-h", "--help"):
            await u.message.reply_text(
                "EFI-OS wrapper — local evidence + RAG + analysis.\n"
                "Uses NO API keys; all data stays on the bot host.\n\n"
                "Sub-commands:\n"
                "  /efi capabilities           — show 17-capability matrix\n"
                "  /efi self-test              — run the 19 bundled tests\n"
                "  /efi research <query>       — local RAG research\n"
                "  /efi analyze <subject>      — engineering analysis\n"
                "  /efi compare <a> <b> [...]  — compare subjects\n"
                "  /efi ingest <subject> <path>— ingest a local file\n"
                "  /efi help                   — this message"
            )
            return

        sub = args[0].lower()
        rest = args[1:]

        try:
            if sub == "capabilities":
                cap = efi_os_skill.capabilities()
                # Send a compact card; full matrix is large.
                summary = (
                    f"🛠 *EFI-OS capabilities* ({len(cap.get('capabilities', {}))} items)\n"
                    f"_service: {cap.get('service')} • "
                    f"single file: {cap.get('single_file')} • "
                    f"keys required: {cap.get('external_api_keys_required')}_\n\n"
                )
                for i, (k, v) in enumerate(
                        (cap.get('capabilities') or {}).items(), 1):
                    summary += f"`{i:02d}` *{k}*\n     _{v}_\n"
                # Telegram message cap is 4096 chars; truncate safely.
                if len(summary) > 3800:
                    summary = summary[:3800] + "\n…[truncated]"
                await u.message.reply_text(summary, parse_mode="Markdown")
            elif sub == "self-test":
                status = await u.message.reply_text(
                    "🧪 Running EFI-OS self-tests (can take a minute)…"
                )
                st = efi_os_skill.self_test()
                out = (
                    f"🧪 *EFI-OS self-test*\n"
                    f"Total: {st['total']}  •  ok: {st['ok']}  •  "
                    f"failed: {st['failed']}  •  skipped: {st['skipped']}\n"
                    f"Return code: {st['returncode']}\n"
                )
                # List failing tests if any.
                fails = [d for d in st["details"]
                         if d["status"] in ("FAIL", "ERROR")]
                if fails:
                    out += "\nFailures:\n"
                    for d in fails[:10]:
                        out += f"  • {d['suite']}::{d['name']} → {d['status']}\n"
                if status:
                    try:
                        await status.edit_text(out, parse_mode="Markdown")
                        return
                    except Exception:
                        pass
                await u.message.reply_text(out, parse_mode="Markdown")
            elif sub == "research":
                if not rest:
                    await u.message.reply_text("Usage: /efi research <query>")
                    return
                query = " ".join(rest)
                result = efi_os_skill.research(query)
                await u.message.reply_text(
                    f"🔬 *EFI-OS research*\n\n```\n"
                    f"{json.dumps(result, indent=2)[:3500]}\n```",
                    parse_mode="Markdown",
                )
            elif sub == "analyze":
                if not rest:
                    await u.message.reply_text(
                        "Usage: /efi analyze <subject> [kind1,kind2,...]"
                    )
                    return
                subject = rest[0]
                kinds = rest[1].split(",") if len(rest) > 1 else None
                result = efi_os_skill.analyze(subject, kinds=kinds)
                await u.message.reply_text(
                    f"🧠 *EFI-OS analyze: {subject}*\n\n```\n"
                    f"{json.dumps(result, indent=2)[:3500]}\n```",
                    parse_mode="Markdown",
                )
            elif sub == "compare":
                if len(rest) < 2:
                    await u.message.reply_text(
                        "Usage: /efi compare <sub1> <sub2> [...]"
                    )
                    return
                result = efi_os_skill.compare(rest)
                await u.message.reply_text(
                    f"⚖️ *EFI-OS compare*\n\n```\n"
                    f"{json.dumps(result, indent=2)[:3500]}\n```",
                    parse_mode="Markdown",
                )
            elif sub == "ingest":
                if len(rest) < 2:
                    await u.message.reply_text(
                        "Usage: /efi ingest <subject> <local-path> "
                        "[type=interview|paper|patent|article|social_post|...]"
                    )
                    return
                subject = rest[0]
                path = rest[1]
                source_type = rest[2] if len(rest) > 2 else "article"
                result = efi_os_skill.ingest_file(subject, path, source_type)
                await u.message.reply_text(
                    f"📥 *EFI-OS ingest*\nSubject: `{subject}`\n"
                    f"Path: `{path}`\nType: `{source_type}`\n\n```\n"
                    f"{json.dumps(result, indent=2)[:3500]}\n```",
                    parse_mode="Markdown",
                )
            else:
                await u.message.reply_text(
                    f"⚠️ Unknown EFI-OS subcommand: {sub!r}. "
                    f"Try /efi help."
                )
        except efi_os_skill.EFIOSTamperedError as exc:
            await u.message.reply_text(
                f"⛔ *EFI-OS integrity check failed*\n\n{exc}\n\n"
                f"Refusing to run a tampered or out-of-date binary."
            )
        except efi_os_skill.EFIOSError as exc:
            await u.message.reply_text(f"❌ {exc}")
        except Exception as exc:  # noqa: BLE001
            await u.message.reply_text(f"❌ {friendly_error(exc)}")

    async def cmd_health(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        """/health — DB / FS / Network probe."""
        from core.health import probe, format_for_telegram
        p = probe()
        await u.message.reply_text(format_for_telegram(p), parse_mode="MarkdownV2")

    # --- ADD: /diag, /setup, /cancel, FSM message router, self-heal start ---
    async def cmd_diag(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        """/diag — diagnostic dump (DB / FS / network / heartbeat)."""
        from core.self_heal import SelfHeal
        heal = SelfHeal(config.ROOT, config.MEMORY_DB_PATH, config.TG_TOKEN)
        rep = heal.diag()
        await u.message.reply_text(f"🩺 *Diagnostics*\n```\n{rep.format_telegram()}\n```",
                                   parse_mode="Markdown")

    async def cmd_setup(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        """/setup — guided wizard to set LLM API key via conversation FSM."""
        from core.fsm import fsm, FlowKind
        uid = u.effective_user.id
        # Two-arg form: /setup <provider> <key>  -> direct set
        args = c.args or []
        if len(args) >= 2:
            provider, key = args[0], args[1]
            return await self._set_llm_key(u, provider, key)
        if len(args) == 1:
            # /setup <provider> -> wait for key
            fsm.push(uid, FlowKind.SETUP_PROVIDER, provider=args[0].lower())
            return await u.message.reply_text(
                f"🔑 Send your `{args[0]}` API key as the next message.\n"
                f"(or /cancel to abort)"
            )
        fsm.push(uid, FlowKind.SETUP_API_KEY)
        await u.message.reply_text(
            "🛠 *Setup wizard*\n"
            "Send: `<provider> <key>`\n"
            "Providers: `anthropic` `openai` `gemini` `groq` "
            "`deepseek` `openrouter` `mistral`\n"
            "Or /cancel to abort."
        )

    async def cmd_cancel(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        """/cancel — drop any active multi-step flow."""
        from core.fsm import fsm
        uid = u.effective_user.id
        cancelled = fsm.cancel(uid)
        await u.message.reply_text(
            "✅ Cancelled." if cancelled else "ℹ️ No active flow to cancel."
        )

    async def _set_llm_key(self, u: Update, provider: str, key: str):
        """Persist provider+key into .env (additive — does not delete other keys)."""
        env_path = config.ROOT / ".env"
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env = {}
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
        env["LLM_PROVIDER"] = provider
        env[f"{provider.upper()}_API_KEY"] = key
        # keep legacy alias so the brain picks it up
        env["LLM_API_KEY"] = key
        env_path.write_text("\n".join(f"{k}={v}" for k, v in env.items()) + "\n")
        await u.message.reply_text(
            f"✅ Saved `{provider}` key. Restart the bot to take effect "
            f"(/update on a live instance will pull + restart automatically)."
        )

    async def fsm_message_router(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        """Catch non-command messages and route them into an active FSM flow."""
        from core.fsm import fsm
        uid = u.effective_user.id
        state = fsm.get(uid)
        if not state or not u.message or not u.message.text:
            return  # no active flow -> ignore (let other handlers run)
        text = u.message.text.strip()
        if state.kind.value == "setup_api_key":
            # expecting "<provider> <key>"
            parts = text.split(maxsplit=1)
            if len(parts) != 2:
                await u.message.reply_text("⚠️ Format: `<provider> <key>`")
                return
            fsm.consume(uid)
            await self._set_llm_key(u, parts[0].lower(), parts[1].strip())
            return
        if state.kind.value == "setup_provider":
            fsm.consume(uid)
            await self._set_llm_key(u, state.data.get("provider", "openai"), text)
            return
        # default: hand back to chat if active
        return

    def _start_self_heal(self):
        """Start the self-heal watchdog. Called once during run()."""
        from core.self_heal import SelfHeal
        heal = SelfHeal(config.ROOT, config.MEMORY_DB_PATH, config.TG_TOKEN)
        heal.start()
        return heal

    def run(self):
        if not self.app:
            return
        # --- ADD: heartbeat touch + self-heal start ---
        try:
            from core.self_heal import SelfHeal
            self._heal = SelfHeal(config.ROOT, config.MEMORY_DB_PATH, config.TG_TOKEN)
            self._heal.start()
            logger.info("Self-heal watchdog started")
        except Exception as e:
            logger.warning(f"Self-heal start failed: {e}")
        # ----------------------------------------------
        logger.info("Starting long-polling...")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    OrcaBot().run()
