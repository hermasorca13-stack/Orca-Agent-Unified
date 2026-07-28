#!/usr/bin/env python3
"""Orca Agent - Simple start script for production deployment"""

import asyncio
import os
import sys
from loguru import logger
from dotenv import load_dotenv

# Ensure project root is in path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core import OrcaAgent
from services.telegram_adapter import OrcaTelegramBot

async def main():
    # Load environment variables
    load_dotenv()
    
    # Ensure logs directory exists
    os.makedirs("logs", exist_ok=True)
    
    logger.info("🦅 Starting Orca-Agent Live Instance...")
    
    # Initialize Core Agent
    agent = OrcaAgent()
    success = await agent.initialize()
    
    if not success:
        logger.error("❌ Failed to initialize Orca Agent core.")
        return

    # Initialize Telegram Bot
    try:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            logger.error("❌ TELEGRAM_BOT_TOKEN not set in environment")
            return
            
        bot = OrcaTelegramBot(agent, token=token)
        await bot.initialize()
        
        # Start bot polling
        logger.info("🤖 Starting Telegram Bot polling...")
        await bot.application.initialize()
        await bot.application.start()
        await bot.application.updater.start_polling(allowed_updates=["message", "callback_query"])
        
        logger.info("✅ Orca-Agent is now LIVE and connected to Telegram!")
        
        # Keep the main loop alive
        while True:
            await asyncio.sleep(3600)
            
    except Exception as e:
        logger.error(f"❌ Error starting Telegram bot: {e}")

if __name__ == "__main__":
    asyncio.run(main())
