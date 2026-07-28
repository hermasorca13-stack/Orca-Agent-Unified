#!/usr/bin/env python3
"""Final bot runner - runs Orca Agent on Telegram with proper logging"""

import os, sys, asyncio, logging
from dotenv import load_dotenv

sys.path.insert(0, "/home/ubuntu/orca-repo")
load_dotenv("/home/ubuntu/orca-repo/.env")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/tmp/orca_bot.log')
    ]
)
logger = logging.getLogger(__name__)

from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "8251930364:AAE2L39B4ltS_vihIePwWpwp0ZuFylngdWo"

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_name = update.effective_user.first_name
    logger.info(f"📨 /start from {user_name} (chat_id: {chat_id})")
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🦅 مرحباً {user_name}!\n\nأنا Orca Agent (هيرمس) - وكيل الذكاء الاصطناعي.\n\nأنا جاهز لأساعدك!\n\n- ابعتلي أي سؤال وأجاوبك\n- ابعتلي ملفات وأحللها\n- اطلب مني أعمل أي حاجة"
    )
    logger.info(f"✅ Replied to {user_name}")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_name = update.effective_user.first_name
    user_text = update.message.text
    logger.info(f"📨 Message from {user_name}: {user_text}")
    
    claude_key = os.getenv("CLAUDE_API_KEY", "")
    if claude_key and claude_key != "placeholder":
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=claude_key)
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1024,
                messages=[{"role": "user", "content": user_text}]
            )
            reply = response.content[0].text
        except Exception as e:
            reply = f"⚠️ Error: {e}"
    else:
        reply = f"🦅 استلمت: {user_text}\n\nOrca Agent جاهز. Claude API key مطلوب للردود الذكية."
    
    await context.bot.send_message(chat_id=chat_id, text=reply)
    logger.info(f"✅ Replied")

async def main():
    logger.info("🦅 Starting Orca Agent Telegram Bot...")
    
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    # Delete webhook if exists
    webhook_info = await application.bot.get_webhook_info()
    if webhook_info.url:
        await application.bot.delete_webhook(drop_pending_updates=True)
        logger.info("🗑️ Deleted webhook")
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling(allowed_updates=["message", "callback_query"])
    
    logger.info("✅ Orca Agent LIVE on Telegram @HermesOrcaXBot")
    logger.info("⏳ Waiting for messages...")
    
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await application.stop()

if __name__ == "__main__":
    asyncio.run(main())
