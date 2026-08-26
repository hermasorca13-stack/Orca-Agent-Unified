import os
from loguru import logger
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

class OrcaTelegramBot:
    def __init__(self, agent, token):
        self.agent = agent
        self.token = token
        self.application = ApplicationBuilder().token(self.token).build()

    async def initialize(self):
        # Add Handlers
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_message))
        self.application.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        logger.info("✅ Telegram Handlers Configured.")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🚀 أهلاً بك يا هندسة! أنا Orca Agent، محركك الهندسي المطور. كيف يمكنني مساعدتك اليوم؟")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_text = update.message.text
        logger.info(f"📩 Telegram Message: {user_text[:50]}")
        
        # Use the unified process_message interface
        response = await self.agent.process_message(user_text, user_id=update.effective_user.id)
        await update.message.reply_text(response)

    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("📸 استلمت الصورة، جاري تحليلها هندسياً...")
        photo_file = await update.message.photo[-1].get_file()
        file_path = f"downloads/{photo_file.file_id}.jpg"
        os.makedirs("downloads", exist_ok=True)
        await photo_file.download_to_drive(file_path)
        
        response = await self.agent.handle_image(file_path)
        await update.message.reply_text(response)


# Compatibility layer for the repository's established Telegram session API.
from dataclasses import dataclass, field
from datetime import datetime, timezone
from telegram.ext import Application


@dataclass
class TelegramUserSession:
    user_id: int
    username: str | None = None
    conversation_history: list[dict] = field(default_factory=list)
    agent_memory: dict = field(default_factory=dict)
    message_count: int = 0

    def add_message(self, role: str, content: str) -> None:
        self.conversation_history.append({"role": role, "content": content, "ts": datetime.now(timezone.utc).isoformat()})
        self.message_count += 1

    def get_recent_history(self, limit: int = 10) -> list[dict]:
        return self.conversation_history[-limit:]

    def clear_history(self) -> None:
        self.conversation_history.clear()
        self.agent_memory.clear()
        self.message_count = 0


_LegacyOrcaTelegramBot = OrcaTelegramBot


class OrcaTelegramBot(_LegacyOrcaTelegramBot):
    def __init__(self, agent, token=None):
        token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN not set")
        super().__init__(agent, token)
        self.user_sessions: dict[int, TelegramUserSession] = {}
        self.active_chats: dict[int, object] = {}

    def _get_user_session(self, user_id: int, username: str | None = None) -> TelegramUserSession:
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = TelegramUserSession(user_id, username)
        elif username and not self.user_sessions[user_id].username:
            self.user_sessions[user_id].username = username
        return self.user_sessions[user_id]

    def get_session_stats(self) -> dict:
        return {
            "total_users": len(self.user_sessions),
            "total_messages": sum(session.message_count for session in self.user_sessions.values()),
            "sessions": [
                {"user_id": session.user_id, "username": session.username, "message_count": session.message_count}
                for session in self.user_sessions.values()
            ],
        }

    async def send_message_to_user(self, user_id: int, text: str) -> None:
        try:
            await self.application.bot.send_message(chat_id=user_id, text=text)
        except Exception as exc:
            logger.error(f"Telegram send failed: {exc}")


async def initialize_telegram_bot(agent, token=None):
    bot = OrcaTelegramBot(agent, token or os.getenv("TELEGRAM_BOT_TOKEN"))
    await bot.initialize()
    return bot
