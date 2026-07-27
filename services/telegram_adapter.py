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

