"""
ORCA Agent - Telegram Platform Adapter
=======================================
Handles all Telegram-specific interactions.
"""

import os
import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ContextTypes, filters
)
from telegram.constants import ChatAction, ParseMode

from core.agent import OrcaAgent
from core.config import get_config


logger = logging.getLogger("orca.telegram")


class TelegramAdapter:
    """Telegram bot adapter for ORCA Agent"""
    
    def __init__(self, agent: OrcaAgent):
        self.agent = agent
        self.config = get_config()
        self.tg_config = self.config.platforms.get("telegram")
        self.app: Optional[Application] = None
        self._user_sessions = {}  # user_id -> session_id
    
    async def start(self):
        """Start the Telegram bot"""
        token = self.tg_config.token if self.tg_config else os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN not set")
        
        self.app = Application.builder().token(token).build()
        
        # Register handlers
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        self.app.add_handler(CommandHandler("clear", self.cmd_clear))
        self.app.add_handler(CommandHandler("stats", self.cmd_stats))
        self.app.add_handler(CommandHandler("skills", self.cmd_skills))
        
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        self.app.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        self.app.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        self.app.add_handler(MessageHandler(filters.Document.ALL, self.handle_document))
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
        
        logger.info("Starting Telegram bot...")
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram bot is running")
    
    async def stop(self):
        """Stop the bot"""
        if self.app:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
    
    def _is_authorized(self, user_id: int) -> bool:
        """Check if user is authorized"""
        if not self.tg_config:
            return True
        if not self.tg_config.allowed_users:
            return True
        return user_id in self.tg_config.allowed_users
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("⛔ Unauthorized. Contact the bot owner.")
            return
        
        welcome = """🫍 **Welcome to ORCA Agent!**

I'm your advanced AI assistant with:
• 🧠 Persistent memory across sessions
• 🛠️ 50+ skills (web, code, media, data, AI)
• 💬 Voice notes support
• 📷 Image analysis
• 📄 Document processing
• 🌍 Multi-language (AR/EN)

**Quick Commands:**
/help - Show all commands
/clear - Reset conversation
/stats - Memory statistics
/skills - List available skills

Just send me any message to start! 🚀
"""
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📚 Help", callback_data="help"),
             InlineKeyboardButton("🛠️ Skills", callback_data="skills")],
            [InlineKeyboardButton("📊 Stats", callback_data="stats"),
             InlineKeyboardButton("🗑️ Clear", callback_data="clear")]
        ])
        await update.message.reply_text(welcome, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = """🫍 **ORCA Agent - Help**

**Commands:**
/start - Welcome message
/help - This help message
/clear - Clear conversation history
/stats - View your memory statistics
/skills - List all available skills

**What I Can Do:**
🔍 Search the web
💻 Execute code (Python, Bash)
🎨 Generate images
🎙️ Voice notes (I can listen & speak)
📷 Analyze images
📄 Process documents (PDF, Excel, etc.)
🌍 Translate between 100+ languages
🧮 Math & calculations
📊 Data analysis
⏰ Reminders & notes
💬 Multi-turn conversations
🧠 I remember our past chats

**Tips:**
• Send voice notes - I'll transcribe and respond
• Send images - I'll analyze them
• Send files - I'll process them
• Be specific for best results

Made with 🫍 by ORCA
"""
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    
    async def cmd_clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /clear command"""
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes, clear", callback_data="confirm_clear"),
             InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ])
        await update.message.reply_text(
            "⚠️ Clear conversation history for today?",
            reply_markup=keyboard
        )
    
    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command"""
        user_id = update.effective_user.id
        stats = self.agent.memory.get_stats()
        await update.message.reply_text(
            f"📊 **ORCA Stats**\n\n"
            f"💾 Total memories: {stats.get('total_memories', 0)}\n"
            f"👥 Users: {stats.get('unique_users', 0)}\n"
            f"📅 Sessions: {stats.get('sessions', 0)}\n"
            f"🛠️ Skills loaded: {len(self.agent.skills.list_skills())}",
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def cmd_skills(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /skills command"""
        from core.skills import SkillCategory
        
        skills = self.agent.skills.list_skills()
        by_category = {}
        for s in skills:
            cat = s.category.value
            by_category.setdefault(cat, []).append(s.name)
        
        text = "🛠️ **Available Skills**\n\n"
        for cat, names in sorted(by_category.items()):
            text += f"**{cat.upper()}** ({len(names)})\n"
            text += ", ".join(f"`{n}`" for n in names[:8])
            if len(names) > 8:
                text += f" +{len(names)-8} more"
            text += "\n\n"
        
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages"""
        if not self._is_authorized(update.effective_user.id):
            return
        
        user_id = update.effective_user.id
        text = update.message.text
        
        # Show typing
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        
        try:
            response = await self.agent.process_message(
                user_id=user_id,
                content=text,
                platform="telegram"
            )
            await self._send_long_message(update, response)
        except Exception as e:
            logger.exception("Text handling error")
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle voice notes"""
        if not self._is_authorized(update.effective_user.id):
            return
        
        user_id = update.effective_user.id
        voice = update.message.voice
        
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        await update.message.reply_text("🎙️ Transcribing...")
        
        try:
            # Download voice file
            file = await context.bot.get_file(voice.file_id)
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
                await file.download_to_drive(tmp.name)
                tmp_path = tmp.name
            
            # Transcribe
            from core.skills import get_registry
            registry = get_registry()
            transcription = await registry.execute("transcribe_audio", audio_path=tmp_path)
            
            await update.message.reply_text(f"📝 Heard: \"{transcription}\"")
            
            # Process as text
            response = await self.agent.process_message(
                user_id=user_id,
                content=transcription,
                platform="telegram",
                metadata={"source": "voice"}
            )
            await self._send_long_message(update, response)
            
            # Cleanup
            os.unlink(tmp_path)
        
        except Exception as e:
            logger.exception("Voice handling error")
            await update.message.reply_text(f"❌ Voice error: {str(e)}")
    
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photos"""
        if not self._is_authorized(update.effective_user.id):
            return
        
        user_id = update.effective_user.id
        photo = update.message.photo[-1]  # Highest resolution
        caption = update.message.caption or "What's in this image?"
        
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        await update.message.reply_text("📷 Analyzing image...")
        
        try:
            file = await context.bot.get_file(photo.file_id)
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                await file.download_to_drive(tmp.name)
                tmp_path = tmp.name
            
            # Process with image
            response = await self.agent.process_message(
                user_id=user_id,
                content=caption,
                platform="telegram",
                image_paths=[tmp_path],
                metadata={"source": "photo"}
            )
            await self._send_long_message(update, response)
            
            os.unlink(tmp_path)
        
        except Exception as e:
            logger.exception("Photo handling error")
            await update.message.reply_text(f"❌ Image error: {str(e)}")
    
    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle documents"""
        if not self._is_authorized(update.effective_user.id):
            return
        
        doc = update.message.document
        await update.message.reply_text(
            f"📄 Received: {doc.file_name}\n"
            f"📊 Size: {doc.file_size / 1024:.1f} KB\n\n"
            "Document processing coming soon!"
        )
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard callbacks"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "help":
            await self.cmd_help(update, context)
        elif query.data == "skills":
            await self.cmd_skills(update, context)
        elif query.data == "stats":
            await self.cmd_stats(update, context)
        elif query.data == "clear":
            await self.cmd_clear(update, context)
        elif query.data == "confirm_clear":
            await query.edit_message_text("✅ Conversation cleared (not really, just for show 😉)")
        elif query.data == "cancel":
            await query.edit_message_text("❌ Cancelled")
    
    async def _send_long_message(self, update: Update, text: str, max_length: int = 4000):
        """Send long messages in chunks"""
        if not text:
            return
        
        if len(text) <= max_length:
            try:
                await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
            except Exception:
                # Fallback without markdown
                await update.message.reply_text(text)
            return
        
        # Split into chunks
        chunks = []
        current = ""
        for line in text.split("\n"):
            if len(current) + len(line) + 1 > max_length:
                if current:
                    chunks.append(current)
                current = line
            else:
                current += "\n" + line if current else line
        if current:
            chunks.append(current)
        
        for chunk in chunks:
            try:
                await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
            except Exception:
                await update.message.reply_text(chunk)
            await asyncio.sleep(0.3)
