"""Telegram webhook routes for Orca Agent"""

from fastapi import APIRouter, Request, HTTPException
from loguru import logger
from telegram import Update
from telegram.ext import Application

router = APIRouter(prefix="/api/telegram", tags=["telegram"])

# This will be set by the main application
telegram_app: Application = None


def set_telegram_app(app: Application):
    """Set the Telegram application instance"""
    global telegram_app
    telegram_app = app


@router.post("/webhook")
async def telegram_webhook(request: Request):
    """
    Telegram webhook endpoint
    Receives updates from Telegram servers
    """
    try:
        data = await request.json()
        
        logger.debug(f"📨 Received Telegram webhook: {data.get('update_id', 'unknown')}")
        
        if not telegram_app:
            logger.error("❌ Telegram app not initialized")
            raise HTTPException(status_code=500, detail="Telegram app not initialized")
        
        # Process the update
        update = Update.de_json(data, telegram_app.bot)
        
        if update:
            await telegram_app.process_update(update)
            logger.debug(f"✅ Processed update {update.update_id}")
        
        return {"ok": True}
        
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/webhook/info")
async def webhook_info():
    """Get webhook information"""
    try:
        if not telegram_app:
            return {"status": "not_initialized"}
        
        webhook_info = await telegram_app.bot.get_webhook_info()
        
        return {
            "status": "active",
            "url": webhook_info.url,
            "has_custom_certificate": webhook_info.has_custom_certificate,
            "pending_update_count": webhook_info.pending_update_count,
            "last_error_date": webhook_info.last_error_date,
            "last_error_message": webhook_info.last_error_message,
        }
    except Exception as e:
        logger.error(f"❌ Error getting webhook info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook/set")
async def set_webhook(webhook_url: str):
    """Set webhook URL"""
    try:
        if not telegram_app:
            raise HTTPException(status_code=500, detail="Telegram app not initialized")
        
        logger.info(f"🔗 Setting webhook URL: {webhook_url}")
        
        await telegram_app.bot.set_webhook(
            url=webhook_url,
            drop_pending_updates=True
        )
        
        logger.info("✅ Webhook URL set successfully")
        
        return {
            "status": "success",
            "webhook_url": webhook_url
        }
        
    except Exception as e:
        logger.error(f"❌ Error setting webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook/delete")
async def delete_webhook():
    """Delete webhook and switch to polling"""
    try:
        if not telegram_app:
            raise HTTPException(status_code=500, detail="Telegram app not initialized")
        
        logger.info("🗑️  Deleting webhook...")
        
        await telegram_app.bot.delete_webhook(drop_pending_updates=True)
        
        logger.info("✅ Webhook deleted successfully")
        
        return {"status": "success", "message": "Webhook deleted"}
        
    except Exception as e:
        logger.error(f"❌ Error deleting webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_telegram_stats():
    """Get Telegram bot statistics"""
    try:
        if not telegram_app:
            return {"status": "not_initialized"}
        
        me = await telegram_app.bot.get_me()
        
        return {
            "bot_id": me.id,
            "bot_username": me.username,
            "bot_first_name": me.first_name,
            "is_bot": me.is_bot,
            "can_join_groups": me.can_join_groups,
            "can_read_all_group_messages": me.can_read_all_group_messages,
            "supports_inline_queries": me.supports_inline_queries,
        }
    except Exception as e:
        logger.error(f"❌ Error getting bot stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
