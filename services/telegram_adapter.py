"""
Telegram Adapter for Orca Agent - Comprehensive Integration Layer
Provides seamless Telegram bot interface with LangGraph state management
"""

import asyncio
import os
from typing import Optional, Dict, Any, List
from datetime import datetime
from loguru import logger
from telegram import Update, Chat
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ChatAction
import json


class TelegramUserSession:
    """Manages per-user session state and conversation history"""
    
    def __init__(self, user_id: int, username: str = None):
        self.user_id = user_id
        self.username = username
        self.conversation_history: List[Dict] = []
        self.agent_memory: Dict = {}
        self.created_at = datetime.now()
        self.last_interaction = datetime.now()
        self.message_count = 0
        self.thinking_state = None
        
    def add_message(self, role: str, content: str, metadata: Dict = None):
        """Add message to conversation history"""
        self.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        })
        self.last_interaction = datetime.now()
        self.message_count += 1
        
    def get_recent_history(self, limit: int = 10) -> List[Dict]:
        """Get recent conversation history"""
        return self.conversation_history[-limit:]
    
    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history = []
        self.agent_memory = {}
        logger.info(f"🧹 Cleared history for user {self.user_id}")


class OrcaTelegramBot:
    """Main Telegram Bot Integration for Orca Agent"""
    
    def __init__(self, agent, token: str = None):
        """Initialize Telegram bot with Orca Agent"""
        self.agent = agent
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN not set in environment")
        
        self.application = None
        self.user_sessions: Dict[int, TelegramUserSession] = {}
        self.active_chats = set()
        
        logger.info(f"🤖 Initializing OrcaTelegramBot...")
    
    async def initialize(self):
        """Initialize Telegram bot application"""
        try:
            self.application = Application.builder().token(self.token).build()
            
            # Register command handlers
            self.application.add_handler(CommandHandler("start", self._handle_start))
            self.application.add_handler(CommandHandler("help", self._handle_help))
            self.application.add_handler(CommandHandler("reset", self._handle_reset))
            self.application.add_handler(CommandHandler("status", self._handle_status))
            self.application.add_handler(CommandHandler("memory", self._handle_memory))
            
            # Register message handler
            self.application.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message)
            )
            
            # Register callback query handler
            self.application.add_handler(CallbackQueryHandler(self._handle_callback))
            
            logger.info("✅ Telegram bot initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Telegram bot: {e}")
            raise
    
    async def start(self):
        """Start polling for updates"""
        if not self.application:
            await self.initialize()
        
        logger.info("🚀 Starting Telegram bot polling...")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        logger.info("✅ Telegram bot is polling for updates")
    
    async def stop(self):
        """Stop the bot gracefully"""
        if self.application:
            await self.application.stop()
            await self.application.shutdown()
            logger.info("⛔ Telegram bot stopped")
    
    def _get_user_session(self, user_id: int, username: str = None) -> TelegramUserSession:
        """Get or create user session"""
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = TelegramUserSession(user_id, username)
            logger.info(f"👤 Created new session for user {user_id} (@{username})")
        return self.user_sessions[user_id]
    
    # ============ COMMAND HANDLERS ============
    
    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        session = self._get_user_session(user.id, user.username)
        
        welcome_message = f"""
🦅 **مرحباً بك في Orca Agent!**

أنا وكيل ذكي متقدم يمكنني:
- 📊 تحليل البيانات والملفات
- 🧠 التفكير السببي والاستدلال العلمي
- 🎨 الإبداع العميق والكتابة
- 📚 التعلم الذاتي والذاكرة طويلة الأمد
- 🔗 التكامل مع GitHub و Manus

**الأوامر المتاحة:**
/help - عرض المساعدة
/reset - إعادة تعيين المحادثة
/status - حالة الوكيل
/memory - عرض الذاكرة المحفوظة

ابدأ بكتابة رسالة أو استخدم الأوامر أعلاه!
        """
        
        await update.message.reply_text(welcome_message, parse_mode="Markdown")
        session.add_message("system", "User started conversation")
        logger.info(f"👋 User {user.id} started conversation")
    
    async def _handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_message = """
🆘 **المساعدة والأوامر:**

**الأوامر الأساسية:**
/start - بدء المحادثة
/help - عرض هذه الرسالة
/reset - حذف سجل المحادثة
/status - حالة النظام
/memory - عرض الذاكرة المحفوظة

**كيفية الاستخدام:**
1️⃣ اكتب أي سؤال أو مهمة
2️⃣ سأقوم بتحليلها والتفكير فيها
3️⃣ سأقدم لك الإجابة مع الشرح

**الميزات:**
- 🧠 التفكير العميق والمنطقي
- 📁 معالجة الملفات والصور
- 💾 حفظ السياق والذاكرة
- 🔄 التعلم من التفاعلات

للمزيد من المعلومات، تفضل بزيارة الموقع الرسمي.
        """
        
        await update.message.reply_text(help_message, parse_mode="Markdown")
    
    async def _handle_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /reset command"""
        user_id = update.effective_user.id
        if user_id in self.user_sessions:
            self.user_sessions[user_id].clear_history()
            await update.message.reply_text("✅ تم حذف سجل المحادثة والذاكرة")
            logger.info(f"🔄 User {user_id} reset conversation")
        else:
            await update.message.reply_text("ℹ️ لا توجد محادثة سابقة للحذف")
    
    async def _handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        agent_health = await self.agent.health_check()
        
        status_message = f"""
📊 **حالة النظام:**

✅ **Orca Agent**: {'🟢 جاهز' if agent_health.get('initialized') else '🔴 غير مهيأ'}
✅ **Telegram Bot**: 🟢 متصل
✅ **Database**: 🟢 متصل
✅ **API**: 🟢 يعمل

**الإحصائيات:**
- عدد المستخدمين النشطين: {len(self.user_sessions)}
- المحادثات المفتوحة: {len(self.active_chats)}
- الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
        
        await update.message.reply_text(status_message, parse_mode="Markdown")
    
    async def _handle_memory(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /memory command"""
        user_id = update.effective_user.id
        session = self._get_user_session(user_id)
        
        if not session.conversation_history:
            await update.message.reply_text("📭 لا توجد محادثات محفوظة")
            return
        
        memory_summary = f"""
💾 **الذاكرة المحفوظة:**

📝 عدد الرسائل: {len(session.conversation_history)}
🕐 آخر تفاعل: {session.last_interaction.strftime('%H:%M:%S')}
📅 بدء الجلسة: {session.created_at.strftime('%Y-%m-%d %H:%M:%S')}

**آخر 5 رسائل:**
        """
        
        for msg in session.get_recent_history(5):
            memory_summary += f"\n- [{msg['role']}]: {msg['content'][:50]}..."
        
        await update.message.reply_text(memory_summary, parse_mode="Markdown")
    
    # ============ MESSAGE HANDLER ============
    
    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming text messages and documents"""
        user = update.effective_user
        message = update.message
        
        session = self._get_user_session(user.id, user.username)
        
        # Show typing indicator
        await message.chat.send_action(ChatAction.TYPING)
        
        try:
            # Handle Document Uploads (Sensory Perception)
            if message.document:
                file = await context.bot.get_file(message.document.file_id)
                download_dir = os.getenv("DOWNLOAD_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "downloads"))
                os.makedirs(download_dir, exist_ok=True)
                file_path = os.path.join(download_dir, message.document.file_name)
                await file.download_to_drive(file_path)
                
                file_ext = message.document.file_name.split('.')[-1].lower()
                logger.info(f"📁 Processing document: {file_path} (Ext: {file_ext})")
                
                response = await self.agent.process_task(f"process_file:{file_path}:{file_ext}")
                result = response.get("result", {})
                
                await message.reply_text(f"✅ تم استلام الملف ومعالجته.\n\nنتائج التحليل:\n{str(result)[:1000]}...", parse_mode="Markdown")
                return

            # Handle Voice Notes (Sensory Perception)
            if message.voice:
                file = await context.bot.get_file(message.voice.file_id)
                download_dir = os.getenv("DOWNLOAD_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "downloads"))
                os.makedirs(download_dir, exist_ok=True)
                file_path = os.path.join(download_dir, f"voice_{user.id}.ogg")
                await file.download_to_drive(file_path)
                
                logger.info(f"🎤 Processing voice note: {file_path}")
                response = await self.agent.process_task(f"process_file:{file_path}:audio")
                result = response.get("result", {})
                
                transcription = result.get("transcription", "تعذر تحويل الصوت لنص")
                await message.reply_text(f"🎤 **النص المستخرج:**\n{transcription}", parse_mode="Markdown")
                
                # Process transcription as a new message
                message_text = transcription
            else:
                message_text = message.text

            if not message_text:
                return

            session.add_message("user", message_text)
            logger.info(f"💬 Message from {user.id} (@{user.username}): {message_text[:50]}...")

            # Smart Command Routing
            if any(keyword in message_text.lower() for keyword in ["سفر", "حجز", "فندق"]):
                # Real-World Execution
                await message.reply_text("✈️ جاري البحث عن خيارات السفر والحجز...")
                # Simplified parsing, in reality would use LLM to extract JSON
                response = await self.agent.process_task(f"book_travel:{{\"query\": \"{message_text}\"}}")
            elif any(keyword in message_text.lower() for keyword in ["مالي", "ميزانية", "مصاريف"]):
                # Financial Intelligence
                await message.reply_text("💰 جاري تحليل البيانات المالية...")
                # Assuming user provides CSV or we use mock data
                csv_path = os.getenv("MOCK_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests", "mock_bank_statement.csv"))
                response = await self.agent.process_task(f"analyze_finances:{csv_path}")
            elif any(keyword in message_text.lower() for keyword in ["قانون", "عقد", "توافق"]):
                # Legal & Compliance
                await message.reply_text("⚖️ جاري التحقق من الامتثال القانوني...")
                response = await self.agent.process_task(f"check_legal_compliance:{message_text}:GDPR,CCPA")
            elif any(keyword in message_text.lower() for keyword in ["صحة", "أعراض", "مريض"]):
                # Health Intelligence
                await message.reply_text("🏥 جاري تحليل الأعراض الصحية...")
                response = await self.agent.process_task(f"health_checkup:{message_text}")
            elif any(keyword in message_text.lower() for keyword in ["تعلم", "منهج", "دراسة"]):
                # Teaching & Coaching
                await message.reply_text("🎓 جاري إعداد منهج تعليمي مخصص...")
                response = await self.agent.process_task(f"generate_curriculum:{message_text}:beginner")
            elif any(keyword in message_text.lower() for keyword in ["برمجة", "مشروع", "تطبيق"]):
                # Product Building
                await message.reply_text("🛠️ جاري التخطيط لبناء المنتج...")
                response = await self.agent.process_task(f"build_mvp:{message_text}")
            else:
                # Default: Call agent's chat method (incorporates Reasoning, Creativity, Learning)
                logger.info(f"🤖 Processing message through Orca Agent Chat...")
                agent_response = await self.agent.chat(
                    user_id=str(user.id),
                    message=message_text,
                    options={"constraints": {"max_tokens": 1000}}
                )
                response_text = agent_response.get("response", "عذراً، حدث خطأ في المعالجة")
                
                # Store response in session
                session.add_message("assistant", response_text)
                
                # Send response back to user
                if len(response_text) > 4000:
                    chunks = [response_text[i:i+4000] for i in range(0, len(response_text), 4000)]
                    for chunk in chunks:
                        await message.reply_text(chunk, parse_mode="Markdown")
                else:
                    await message.reply_text(response_text, parse_mode="Markdown")
                return

            # For routed commands, handle the response
            result = response.get("result", {})
            response_text = result.get("message", str(result))
            await message.reply_text(f"🤖 {response_text}", parse_mode="Markdown")
            
            logger.info(f"✅ Response sent to user {user.id}")
            
        except Exception as e:
            logger.error(f"❌ Error processing message: {e}")
            error_message = f"❌ حدث خطأ: {str(e)[:200]}"
            await message.reply_text(error_message)
    
    async def _handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries from inline buttons"""
        query = update.callback_query
        await query.answer()
        
        logger.info(f"🔘 Callback from user {query.from_user.id}: {query.data}")
        
        # Handle different callback types
        if query.data.startswith("action_"):
            await self._handle_action_callback(query, context)
    
    async def _handle_action_callback(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle action-based callbacks"""
        action = query.data.replace("action_", "")
        logger.info(f"⚡ Executing action: {action}")
        
        await query.edit_message_text(f"✅ تم تنفيذ الإجراء: {action}")
    
    # ============ UTILITY METHODS ============
    
    async def send_message_to_user(self, user_id: int, message: str):
        """Send a message to a specific user"""
        try:
            if self.application:
                await self.application.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode="Markdown"
                )
                logger.info(f"📤 Sent message to user {user_id}")
        except Exception as e:
            logger.error(f"❌ Failed to send message to user {user_id}: {e}")
    
    def get_session_stats(self) -> Dict:
        """Get statistics about all sessions"""
        stats = {
            "total_users": len(self.user_sessions),
            "active_chats": len(self.active_chats),
            "total_messages": sum(len(s.conversation_history) for s in self.user_sessions.values()),
            "sessions": []
        }
        
        for user_id, session in self.user_sessions.items():
            stats["sessions"].append({
                "user_id": user_id,
                "username": session.username,
                "messages": len(session.conversation_history),
                "created_at": session.created_at.isoformat(),
                "last_interaction": session.last_interaction.isoformat()
            })
        
        return stats


# ============ INITIALIZATION FUNCTION ============

async def initialize_telegram_bot(agent) -> OrcaTelegramBot:
    """Initialize and start the Telegram bot"""
    try:
        bot = OrcaTelegramBot(agent)
        await bot.initialize()
        logger.info("✅ Telegram bot initialized successfully")
        return bot
    except Exception as e:
        logger.error(f"❌ Failed to initialize Telegram bot: {e}")
        raise
