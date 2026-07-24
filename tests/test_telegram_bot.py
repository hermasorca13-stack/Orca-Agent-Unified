"""
Comprehensive tests for Telegram bot integration with Orca Agent
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
from services.telegram_adapter import (
    TelegramUserSession,
    OrcaTelegramBot,
    initialize_telegram_bot
)


class TestTelegramUserSession:
    """Test TelegramUserSession class"""
    
    def test_session_initialization(self):
        """Test session initialization"""
        session = TelegramUserSession(user_id=12345, username="testuser")
        
        assert session.user_id == 12345
        assert session.username == "testuser"
        assert session.conversation_history == []
        assert session.agent_memory == {}
        assert session.message_count == 0
    
    def test_add_message(self):
        """Test adding messages to session"""
        session = TelegramUserSession(user_id=12345)
        
        session.add_message("user", "Hello")
        assert len(session.conversation_history) == 1
        assert session.conversation_history[0]["role"] == "user"
        assert session.conversation_history[0]["content"] == "Hello"
        assert session.message_count == 1
    
    def test_get_recent_history(self):
        """Test retrieving recent conversation history"""
        session = TelegramUserSession(user_id=12345)
        
        for i in range(15):
            session.add_message("user" if i % 2 == 0 else "assistant", f"Message {i}")
        
        recent = session.get_recent_history(5)
        assert len(recent) == 5
        assert recent[0]["content"] == "Message 10"
        assert recent[-1]["content"] == "Message 14"
    
    def test_clear_history(self):
        """Test clearing conversation history"""
        session = TelegramUserSession(user_id=12345)
        
        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi there")
        session.agent_memory["test"] = "value"
        
        assert len(session.conversation_history) == 2
        
        session.clear_history()
        
        assert len(session.conversation_history) == 0
        assert session.agent_memory == {}


class TestOrcaTelegramBot:
    """Test OrcaTelegramBot class"""
    
    @pytest.fixture
    def mock_agent(self):
        """Create a mock Orca Agent"""
        agent = AsyncMock()
        agent.health_check = AsyncMock(return_value={"initialized": True})
        agent.chat = AsyncMock(return_value={
            "response": "Test response",
            "tokensUsed": 50,
            "cost": 0.001
        })
        return agent
    
    @pytest.fixture
    def telegram_bot(self, mock_agent):
        """Create a TelegramBot instance with mocked token"""
        with patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': 'test_token_12345'}):
            bot = OrcaTelegramBot(mock_agent, token='test_token_12345')
            return bot
    
    def test_bot_initialization(self, telegram_bot):
        """Test bot initialization"""
        assert telegram_bot.token == 'test_token_12345'
        assert len(telegram_bot.user_sessions) == 0
        assert len(telegram_bot.active_chats) == 0
    
    def test_get_user_session(self, telegram_bot):
        """Test getting or creating user session"""
        session = telegram_bot._get_user_session(12345, "testuser")
        
        assert session.user_id == 12345
        assert session.username == "testuser"
        assert 12345 in telegram_bot.user_sessions
        
        # Getting same session again should return same instance
        session2 = telegram_bot._get_user_session(12345)
        assert session is session2
    
    def test_get_session_stats(self, telegram_bot):
        """Test getting session statistics"""
        # Create multiple sessions
        telegram_bot._get_user_session(111, "user1")
        telegram_bot._get_user_session(222, "user2")
        
        # Add messages to sessions
        telegram_bot.user_sessions[111].add_message("user", "Hello")
        telegram_bot.user_sessions[222].add_message("user", "Hi")
        telegram_bot.user_sessions[222].add_message("assistant", "Hello")
        
        stats = telegram_bot.get_session_stats()
        
        assert stats["total_users"] == 2
        assert stats["total_messages"] == 3
        assert len(stats["sessions"]) == 2
    
    @pytest.mark.asyncio
    async def test_send_message_to_user(self, telegram_bot):
        """Test sending message to user"""
        telegram_bot.application = AsyncMock()
        telegram_bot.application.bot = AsyncMock()
        telegram_bot.application.bot.send_message = AsyncMock()
        
        await telegram_bot.send_message_to_user(12345, "Test message")
        
        telegram_bot.application.bot.send_message.assert_called_once()


class TestTelegramIntegration:
    """Integration tests for Telegram bot with Orca Agent"""
    
    @pytest.mark.asyncio
    async def test_initialize_telegram_bot(self):
        """Test initializing Telegram bot"""
        mock_agent = AsyncMock()
        mock_agent.health_check = AsyncMock(return_value={"initialized": True})
        
        with patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': 'test_token'}):
            with patch('services.telegram_adapter.Application'):
                bot = await initialize_telegram_bot(mock_agent)
                
                assert bot is not None
                assert bot.agent == mock_agent
    
    @pytest.mark.asyncio
    async def test_message_flow(self):
        """Test complete message flow"""
        mock_agent = AsyncMock()
        mock_agent.health_check = AsyncMock(return_value={"initialized": True})
        mock_agent.chat = AsyncMock(return_value={
            "response": "This is a test response",
            "tokensUsed": 100,
            "cost": 0.002
        })
        
        with patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': 'test_token'}):
            bot = OrcaTelegramBot(mock_agent)
            
            # Simulate user message
            user_id = 12345
            message = "What is AI?"
            
            session = bot._get_user_session(user_id, "testuser")
            session.add_message("user", message)
            
            # Verify message was added
            assert len(session.conversation_history) == 1
            assert session.conversation_history[0]["content"] == message
            
            # Simulate agent response
            response = await mock_agent.chat(
                user_id=str(user_id),
                message=message,
                options={"constraints": {"max_tokens": 1000}}
            )
            
            session.add_message("assistant", response["response"])
            
            # Verify conversation history
            assert len(session.conversation_history) == 2
            assert session.conversation_history[1]["role"] == "assistant"


class TestErrorHandling:
    """Test error handling in Telegram bot"""
    
    def test_missing_token(self):
        """Test initialization without token"""
        mock_agent = Mock()
        
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN not set"):
                OrcaTelegramBot(mock_agent)
    
    @pytest.mark.asyncio
    async def test_send_message_error(self):
        """Test error handling when sending message fails"""
        mock_agent = Mock()
        
        with patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': 'test_token'}):
            bot = OrcaTelegramBot(mock_agent)
            bot.application = AsyncMock()
            bot.application.bot = AsyncMock()
            bot.application.bot.send_message = AsyncMock(
                side_effect=Exception("Send failed")
            )
            
            # Should not raise, just log error
            await bot.send_message_to_user(12345, "Test")


class TestSessionManagement:
    """Test session management features"""
    
    def test_multiple_user_sessions(self):
        """Test managing multiple user sessions"""
        mock_agent = Mock()
        
        with patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': 'test_token'}):
            bot = OrcaTelegramBot(mock_agent)
            
            # Create sessions for multiple users
            users = [111, 222, 333, 444, 555]
            for user_id in users:
                session = bot._get_user_session(user_id, f"user{user_id}")
                for i in range(5):
                    session.add_message("user", f"Message {i}")
            
            assert len(bot.user_sessions) == 5
            
            stats = bot.get_session_stats()
            assert stats["total_users"] == 5
            assert stats["total_messages"] == 25
    
    def test_session_memory_persistence(self):
        """Test that session memory persists across interactions"""
        mock_agent = Mock()
        
        with patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': 'test_token'}):
            bot = OrcaTelegramBot(mock_agent)
            
            session = bot._get_user_session(12345)
            
            # Add data to memory
            session.agent_memory["key1"] = "value1"
            session.agent_memory["key2"] = {"nested": "data"}
            
            # Verify persistence
            assert session.agent_memory["key1"] == "value1"
            assert session.agent_memory["key2"]["nested"] == "data"
            
            # Get same session again
            session2 = bot._get_user_session(12345)
            assert session2.agent_memory == session.agent_memory


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
