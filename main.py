#!/usr/bin/env python3
"""Orca Agent - Main entry point with Telegram Integration"""

import asyncio
import os
import signal
from loguru import logger
from dotenv import load_dotenv
import sys

# Ensure project root is in path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.api import app, agent
from services.telegram_adapter import initialize_telegram_bot
import uvicorn


# Load environment variables
load_dotenv()

# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)

# Configure logging
logger.remove()  # Remove default handler
logger.add(
    "logs/orca_agent.log",
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    rotation="500 MB"
)
logger.add(
    lambda msg: print(msg, end=""),
    colorize=True,
    format="<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)

# Global telegram bot instance
telegram_bot = None
server = None


async def initialize_agent():
    """Initialize Orca Agent core"""
    logger.info("🦅 ════════════════════════════════════════════════════════")
    logger.info("🦅 ORCA AGENT - Advanced Multi-Tier AI Framework v1.0.0")
    logger.info("🦅 ════════════════════════════════════════════════════════")
    
    # Verify configuration
    logger.info("🔍 Verifying configuration...")
    required_keys = {
        "CLAUDE_API_KEY": "Claude API key",
        "GITHUB_TOKEN": "GitHub token",
        "MANUS_API_KEY": "Manus API key",
        "TELEGRAM_BOT_TOKEN": "Telegram bot token"
    }
    
    for key, description in required_keys.items():
        if not os.getenv(key):
            logger.warning(f"⚠️  {description} ({key}) not set")
        else:
            logger.info(f"✅ {description} configured")
    
    logger.info("✅ Configuration verified")
    
    # Initialize Orca Agent
    logger.info("🚀 Initializing Orca Agent core...")
    success = await agent.initialize()
    
    if not success:
        logger.error("❌ Failed to initialize Orca Agent")
        return False
    
    logger.info("✅ Orca Agent initialized successfully")
    return True


async def initialize_telegram():
    """Initialize Telegram bot"""
    global telegram_bot
    
    try:
        logger.info("📱 Initializing Telegram bot...")
        telegram_bot = await initialize_telegram_bot(agent)
        logger.info("✅ Telegram bot initialized successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to initialize Telegram bot: {e}")
        return False


async def start_fastapi_server():
    """Start FastAPI server"""
    global server
    
    port = int(os.getenv("PORT", 8000))
    logger.info(f"🚀 Starting FastAPI server on port {port}...")
    
    config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=port,
        log_level=os.getenv("LOG_LEVEL", "info").lower()
    )
    server = uvicorn.Server(config)
    
    try:
        await server.serve()
    except Exception as e:
        logger.error(f"❌ FastAPI server error: {e}")


async def start_telegram_polling():
    """Start Telegram bot polling"""
    global telegram_bot
    
    if telegram_bot:
        try:
            logger.info("📱 Starting Telegram bot polling...")
            await telegram_bot.start()
        except Exception as e:
            logger.error(f"❌ Telegram bot error: {e}")


async def main():
    """Main async entry point"""
    try:
        # Initialize Orca Agent
        if not await initialize_agent():
            logger.error("❌ Failed to initialize Orca Agent")
            return
        
        # Initialize Telegram bot
        if not await initialize_telegram():
            logger.warning("⚠️  Telegram bot initialization failed, continuing without it")
        
        # Create tasks for concurrent execution
        tasks = []
        
        # Add FastAPI server task
        tasks.append(asyncio.create_task(start_fastapi_server()))
        
        # Add Telegram polling task if bot is available
        if telegram_bot:
            tasks.append(asyncio.create_task(start_telegram_polling()))
        
        logger.info("🚀 All services started successfully!")
        logger.info("🦅 ════════════════════════════════════════════════════════")
        
        # Wait for all tasks
        await asyncio.gather(*tasks)
        
    except KeyboardInterrupt:
        logger.info("\n⛔ Shutting down Orca Agent...")
        logger.info("🦅 ════════════════════════════════════════════════════════")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        raise
    finally:
        # Cleanup
        if telegram_bot:
            try:
                await telegram_bot.stop()
            except Exception as e:
                logger.error(f"Error stopping Telegram bot: {e}")
        
        if server:
            try:
                await server.shutdown()
            except Exception as e:
                logger.error(f"Error stopping FastAPI server: {e}")


def signal_handler(sig, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {sig}, shutting down...")
    raise KeyboardInterrupt()


if __name__ == "__main__":
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("✅ Orca Agent shutdown complete")
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        raise
