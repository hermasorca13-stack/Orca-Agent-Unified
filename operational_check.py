import os
import asyncio
from telegram import Bot
from loguru import logger

async def check_bot_status():
    token = "8251930364:AAE2L39B4ltS_vihIePwWpwp0ZuFylngdWo"
    bot = Bot(token=token, request=None)
    try:
        me = await bot.get_me()
        logger.info(f"✅ Bot is ONLINE: @{me.username} ({me.first_name})")
        
        # Test if bot can fetch updates (even if empty)
        updates = await bot.get_updates(limit=1)
        logger.info(f"✅ Connection to Telegram API is STABLE. Fetched {len(updates)} updates.")
        return True
    except Exception as e:
        logger.error(f"❌ Bot Status Check FAILED: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(check_bot_status())
