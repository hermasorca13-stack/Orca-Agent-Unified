# telegram_bot/bot.py - Orca Agent Telegram Bot (Production)
"""
Real Telegram Bot connection using long-polling.
Bot: @HermesOrcaXBot
Token: from .env (TELEGRAM_BOT_TOKEN)
"""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from loguru import logger
from core.config import config

class OrcaBot:
    def __init__(self):
        self.app = None
        self.authorized_users = set()  # populated on /start
        self._build()

    def _build(self):
        if not config.TG_TOKEN:
            logger.error("TELEGRAM_BOT_TOKEN missing")
            return
        self.app = Application.builder().token(config.TG_TOKEN).build()
        self._register_handlers()
        logger.info(f"Bot application built | @{config.TG_USERNAME}")

    def _register_handlers(self):
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CommandHandler("skills", self.cmd_skills))
        self.app.add_handler(CommandHandler("sync", self.cmd_sync))
        self.app.add_handler(CommandHandler("device", self.cmd_device))
        self.app.add_handler(CommandHandler("exec", self.cmd_exec))
        self.app.add_handler(CommandHandler("token", self.cmd_token))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_message))

    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        self.authorized_users.add(user.id)
        await update.message.reply_text(
            f"🐋 Orca Agent Online\n"
            f"User: {user.first_name} (id={user.id})\n"
            f"Bot: @{config.TG_USERNAME}\n"
            f"Repo: {config.GH_REPO}\n\n"
            f"Commands: /status /skills /sync /device /exec /token"
        )
        logger.info(f"User authorized: {user.id} | {user.username}")

    async def cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        from api_manager.api_manager import api
        await update.message.reply_text(
            f"📊 Orca Status\n"
            f"Bot: ✅ @{config.TG_USERNAME}\n"
            f"GitHub: {config.GH_REPO} @ {config.GH_BRANCH}\n"
            f"Tokens: {len(api.tokens)}\n"
            f"Mode: {config.RUN_MODE}\n"
            f"ADB: {config.ADB_HOST}:{config.ADB_PORT}"
        )

    async def cmd_skills(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        skills_dir = config.SKILLS_PATH
        skills = [f.stem for f in skills_dir.glob("*.py")] if skills_dir.exists() else []
        await update.message.reply_text(f"🧠 Loaded skills ({len(skills)}):\n" + "\n".join(f"• {s}" for s in skills))

    async def cmd_sync(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        from github_sync.gh_sync import sync_to_github
        await update.message.reply_text("🔄 Syncing to GitHub...")
        result = sync_to_github()
        await update.message.reply_text(f"{'✅' if result['ok'] else '❌'} {result['msg']}")

    async def cmd_device(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        from android_bridge.adb_controller import get_device_info
        info = get_device_info()
        await update.message.reply_text(f"📱 Device:\n{info}")

    async def cmd_exec(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        args = ctx.args
        if not args:
            await update.message.reply_text("Usage: /exec <command>")
            return
        cmd = " ".join(args)
        from skills.shell_executor import run
        result = run(cmd, timeout=30)
        out = (result.get("stdout") or "")[:1500]
        await update.message.reply_text(f"$ {cmd}\n```\n{out}\n```"[:4000], parse_mode="Markdown")

    async def cmd_token(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        from api_manager.api_manager import api
        tok = api.create_token(name=f"tg_{update.effective_user.id}")
        await update.message.reply_text(f"🔑 New token:\n`{tok}`", parse_mode="Markdown")

    async def on_message(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        text = update.message.text or ""
        await update.message.reply_text(f"🤖 Received: {text[:200]}\nUse /status, /skills, /sync, /exec, /device")

    def run(self):
        if not self.app:
            logger.error("App not built — token missing")
            return
        logger.info("Starting bot (long-polling)...")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    OrcaBot().run()
