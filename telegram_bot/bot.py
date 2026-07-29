# telegram_bot/bot.py - Orca Agent Telegram Bot (Unified, Single Source)
"""
Real Telegram bot using long-polling.
- Bot: @HermesOrcaXBot
- Commands: /start /status /skills /sync /device /exec /token /tap /swipe /text
- All handlers share the same APIManager and config singletons.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
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
        h(CommandHandler("health", self.cmd_health))
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
                BotCommand("pdf", "Read PDF (info/text/tables)"),
                BotCommand("wiki", "Wikipedia search/summary"),
                BotCommand("say", "Text-to-speech (edge-tts, no key)"),
                BotCommand("news", "News headlines (Google News RSS)"),
                BotCommand("fx", "Currency exchange (Frankfurter, no key)"),
                BotCommand("arxiv", "Search arXiv papers"),
                BotCommand("health", "DB / FS / Network probe"),
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
            f"Library-backed skills:\n"
            f"/gh <op> — GitHub (PyGithub)\n"
            f"/crypto <op> — Markets (pycoingecko)\n"
            f"/stock <ticker> — Quote (yfinance)\n"
            f"/qr <text> — QR code (qrcode)\n"
            f"/short <url> — Shortener (pyshorteners)"
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

    async def cmd_skills(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        from skills.orca_skills import load_all
        loaded = load_all()
        await u.message.reply_text(f"🧠 Skills ({len(loaded)}):\n" + "\n".join(f"• {k}" for k in loaded))

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
        # Fallback: echo + command hint (full menu, including the 5 library-backed skills)
        fallback = (
            f"Received: {text[:200]}\n\n"
            f"🧠 Brain offline — rule-based mode.\n"
            f"Available commands:\n"
            f"• /start /status /skills /sync /update /verify\n"
            f"• /exec /token /brain /agent /device\n"
            f"• /tap /swipe /text\n"
            f"• /gh /crypto /stock /qr /short\n\n"
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
                "Usage: /pdf info <path>\n"
                "       /pdf text <path> [page]\n"
                "       /pdf tables <path> [page]"
            )
            return
        op = args[0].lower()
        path = args[1] if len(args) > 1 else ""
        try:
            if op == "info":
                meta = pdf_skill.info(path)
                out = (
                    f"📄 *{meta.get('title') or path}*\n"
                    f"Pages: {meta.get('pages')}\n"
                    f"Author: {meta.get('author') or '—'}\n"
                    f"Size: {meta.get('size_bytes')} bytes"
                )
            elif op == "text":
                page = int(args[2]) if len(args) > 2 else None
                body = pdf_skill.text(path, page=page)
                out = body[:3500] + ("\n…[truncated]" if len(body) > 3500 else "")
            elif op == "tables":
                page = int(args[2]) if len(args) > 2 else None
                tables = pdf_skill.tables(path, page=page)
                if not tables:
                    out = "📭 No tables found on that page"
                else:
                    lines = [f"📊 {len(tables)} table(s) found", ""]
                    for i, t in enumerate(tables[:3], 1):
                        lines.append(f"*Table {i}* ({len(t)} rows)")
                        for row in t[:5]:
                            lines.append(" | ".join(row))
                        lines.append("")
                    out = "\n".join(lines)
            else:
                out = f"⚠️ Unknown op: {op}. Use info|text|tables."
        except Exception as e:
            out = friendly_error(e)
        await u.message.reply_text(out, parse_mode="Markdown")

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

    async def cmd_health(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        """/health — DB / FS / Network probe."""
        from core.health import probe, format_for_telegram
        p = probe()
        await u.message.reply_text(format_for_telegram(p), parse_mode="MarkdownV2")

    def run(self):
        if not self.app:
            return
        logger.info("Starting long-polling...")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    OrcaBot().run()
