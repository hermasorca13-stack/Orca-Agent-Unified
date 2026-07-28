# telegram_bot/bot.py - Orca Agent Telegram Bot (Unified, Single Source)
"""
Real Telegram bot using long-polling.
- Bot: @HermesOrcaXBot
- Commands: /start /status /skills /sync /device /exec /token /tap /swipe /text
- All handlers share the same APIManager and config singletons.
"""
import asyncio
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
        h(CommandHandler("status", self.cmd_status))
        h(CommandHandler("skills", self.cmd_skills))
        h(CommandHandler("sync", self.cmd_sync))
        h(CommandHandler("device", self.cmd_device))
        h(CommandHandler("exec", self.cmd_exec))
        h(CommandHandler("token", self.cmd_token))
        h(CommandHandler("tap", self.cmd_tap))
        h(CommandHandler("swipe", self.cmd_swipe))
        h(CommandHandler("text", self.cmd_text))
        h(MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_text))

    # ---- Handlers ----
    async def cmd_start(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        user = u.effective_user
        self.authorized.add(user.id)
        await u.message.reply_text(
            f"🐋 Orca Agent Online\n"
            f"User: {user.first_name} (id={user.id})\n"
            f"Bot: @{config.TG_USERNAME}\n"
            f"Repo: {config.GH_REPO}\n"
            f"Tokens: {api.count()}\n\n"
            f"Commands:\n"
            f"/status /skills /sync /device\n"
            f"/exec <cmd> /token\n"
            f"/tap <x> <y> /swipe <x1> <y1> <x2> <y2> /text <msg>"
        )

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

    async def on_text(self, u: Update, c: ContextTypes.DEFAULT_TYPE):
        await u.message.reply_text(
            f"Received: {u.message.text[:200]}\n"
            f"Use /status /skills /sync /exec /device /token /tap /swipe /text"
        )

    def run(self):
        if not self.app:
            return
        logger.info("Starting long-polling...")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    OrcaBot().run()
