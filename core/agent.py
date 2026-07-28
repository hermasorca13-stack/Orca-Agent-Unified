"""
ORCA Agent - Main Agent Class
=============================
The core agent that orchestrates LLM, memory, skills, and platforms.
"""

import os
import json
import asyncio
import logging
import hashlib
from typing import List, Dict, Any, Optional, AsyncGenerator
from datetime import datetime

from .config import OrcaConfig, get_config
from .memory import MemorySystem
from .memory_instance import get_memory
from .skills import SkillRegistry, get_registry, SkillCategory


logger = logging.getLogger("orca.agent")


class OrcaAgent:
    """
    Main ORCA Agent - the brain that coordinates everything.
    """
    
    SYSTEM_PROMPT = """You are ORCA 🫍, an advanced AI agent with deep capabilities.

# Your Identity
You are ORCA (Open-source Responsive Cognitive Assistant), a self-improving AI agent built to help users accomplish any task with intelligence, creativity, and care.

# Core Principles
1. **Helpful first** - Always prioritize the user's actual goal
2. **Transparent** - Explain what you're doing and why
3. **Safe** - Never take destructive actions without explicit confirmation
4. **Persistent** - Remember context across conversations
5. **Multi-modal** - Handle text, voice, images, and files seamlessly
6. **Tool-using** - Leverage available skills to accomplish real tasks

# Available Capabilities
You have access to many skills you can invoke by name. Use them when appropriate:
{skills_description}

# Response Style
- Be conversational but precise
- Use markdown for clarity (bold, lists, code blocks)
- For complex answers, structure with headers
- When using tools, briefly explain what you're doing
- If uncertain, say so honestly
- Match the user's language (Arabic, English, or mixed)

# Important
- You have memory of past conversations - use it to personalize
- You can handle files, images, voice notes, and documents
- You run 24/7 and can be reached via Telegram
- Your owner is the user, not anyone else

# Current Context
- User: {user_id}
- Session: {session_id}
- Platform: {platform}
- Time: {current_time}
"""
    
    def __init__(self, config: Optional[OrcaConfig] = None):
        self.config = config or get_config()
        self.memory = get_memory()
        self.skills = get_registry()
        self._llm_client = None
        self._init_llm()
    
    def _init_llm(self):
        """Initialize the LLM client based on config"""
        provider = self.config.llm.provider
        
        if provider.value == "openai" and self.config.llm.api_key:
            from openai import AsyncOpenAI
            self._llm_client = AsyncOpenAI(
                api_key=self.config.llm.api_key,
                base_url=self.config.llm.base_url
            )
            logger.info(f"LLM initialized: OpenAI ({self.config.llm.model})")
        
        elif provider.value == "anthropic" and self.config.llm.api_key:
            from anthropic import AsyncAnthropic
            self._llm_client = AsyncAnthropic(api_key=self.config.llm.api_key)
            logger.info(f"LLM initialized: Anthropic ({self.config.llm.model})")
        
        elif provider.value == "deepseek" and self.config.llm.api_key:
            from openai import AsyncOpenAI
            self._llm_client = AsyncOpenAI(
                api_key=self.config.llm.api_key,
                base_url=self.config.llm.base_url or "https://api.deepseek.com/v1"
            )
            logger.info(f"LLM initialized: DeepSeek ({self.config.llm.model})")
        
        elif provider.value == "openrouter" and self.config.llm.api_key:
            from openai import AsyncOpenAI
            self._llm_client = AsyncOpenAI(
                api_key=self.config.llm.api_key,
                base_url=self.config.llm.base_url or "https://openrouter.ai/api/v1"
            )
            logger.info(f"LLM initialized: OpenRouter ({self.config.llm.model})")
        
        else:
            logger.warning("No LLM client initialized - check API keys")
    
    def _build_system_prompt(self, user_id: int, session_id: str, platform: str) -> str:
        """Build the system prompt with context"""
        # Get user facts
        user_data = self.memory.get_user_facts(user_id)
        facts_str = json.dumps(user_data.get("facts", {}), ensure_ascii=False)
        
        skills_desc = self.skills.get_skills_description()
        
        prompt = self.SYSTEM_PROMPT.format(
            skills_description=skills_desc or "No skills registered yet.",
            user_id=user_id,
            session_id=session_id,
            platform=platform,
            current_time=datetime.now().isoformat()
        )
        
        if facts_str and facts_str != "{}":
            prompt += f"\n\n# Known Facts About This User\n{facts_str}"
        
        return prompt
    
    def _make_session_id(self, user_id: int, platform: str) -> str:
        """Generate a session ID"""
        today = datetime.now().strftime("%Y%m%d")
        return f"{platform}_{user_id}_{today}"
    
    async def process_message(
        self,
        user_id: int,
        content: str,
        platform: str = "telegram",
        session_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        image_paths: Optional[List[str]] = None
    ) -> str:
        """
        Process a user message and return a response.
        """
        if not session_id:
            session_id = self._make_session_id(user_id, platform)
        
        self.memory.create_session(session_id, user_id, platform)
        
        # Add user message to memory
        self.memory.add_memory(
            user_id=user_id,
            session_id=session_id,
            role="user",
            content=content,
            metadata=metadata or {},
            importance=0.6
        )
        
        # Get relevant context
        context = self.memory.get_relevant_context(
            user_id=user_id,
            current_query=content,
            session_id=session_id,
            max_tokens=8000
        )
        
        # Build messages
        system_prompt = self._build_system_prompt(user_id, session_id, platform)
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(context)
        
        # Add current message with images if any
        if image_paths:
            content_parts = [{"type": "text", "text": content}]
            for img_path in image_paths:
                try:
                    import base64
                    with open(img_path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode()
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
                    })
                except Exception as e:
                    logger.error(f"Image read error: {e}")
            messages.append({"role": "user", "content": content_parts})
        else:
            messages.append({"role": "user", "content": content})
        
        # Get LLM response
        try:
            response_text, tool_calls = await self._call_llm(messages)
            
            # Handle tool calls if any
            if tool_calls:
                response_text = await self._handle_tool_calls(
                    messages, tool_calls, user_id, session_id
                )
        
        except Exception as e:
            logger.exception("LLM call failed")
            response_text = f"⚠️ I encountered an error: {str(e)}\n\nPlease try again or rephrase your request."
        
        # Save assistant response
        self.memory.add_memory(
            user_id=user_id,
            session_id=session_id,
            role="assistant",
            content=response_text,
            importance=0.5
        )
        
        return response_text
    
    async def _call_llm(self, messages: List[Dict]) -> tuple[str, Optional[List[Dict]]]:
        """Call the LLM and return (text, tool_calls)"""
        if not self._llm_client:
            return (
                "⚠️ LLM not configured. Please set OPENAI_API_KEY, ANTHROPIC_API_KEY, or DEEPSEEK_API_KEY.",
                None
            )
        
        provider = self.config.llm.provider
        
        if provider.value in ["openai", "deepseek", "openrouter"]:
            tools = self.skills.get_tool_schemas() if self.config.skills.auto_load else None
            
            kwargs = {
                "model": self.config.llm.model,
                "messages": messages,
                "temperature": self.config.llm.temperature,
                "max_tokens": self.config.llm.max_tokens,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            
            response = await self._llm_client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            text = choice.message.content or ""
            tool_calls = None
            if hasattr(choice.message, 'tool_calls') and choice.message.tool_calls:
                tool_calls = [
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": json.loads(tc.function.arguments)
                    }
                    for tc in choice.message.tool_calls
                ]
            return text, tool_calls
        
        elif provider.value == "anthropic":
            # Extract system message
            system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
            api_messages = [m for m in messages if m["role"] != "system"]
            
            response = await self._llm_client.messages.create(
                model=self.config.llm.model,
                system=system_msg,
                messages=api_messages,
                max_tokens=self.config.llm.max_tokens,
                temperature=self.config.llm.temperature
            )
            return response.content[0].text, None
        
        return "⚠️ Unknown LLM provider", None
    
    async def _handle_tool_calls(
        self,
        messages: List[Dict],
        tool_calls: List[Dict],
        user_id: int,
        session_id: str
    ) -> str:
        """Execute tool calls and get final response"""
        # Execute each tool call
        tool_results = []
        for tc in tool_calls:
            try:
                logger.info(f"Executing tool: {tc['name']} with args: {tc['arguments']}")
                result = await self.skills.execute(tc["name"], **tc["arguments"])
                tool_results.append({
                    "tool_call_id": tc["id"],
                    "role": "tool",
                    "name": tc["name"],
                    "content": str(result)[:4000]
                })
            except Exception as e:
                logger.exception(f"Tool {tc['name']} failed")
                tool_results.append({
                    "tool_call_id": tc["id"],
                    "role": "tool",
                    "name": tc["name"],
                    "content": f"Error: {str(e)}"
                })
        
        # Get final response with tool results
        messages.extend([
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"])
                        }
                    }
                    for tc in tool_calls
                ]
            },
            *tool_results
        ])
        
        final_text, _ = await self._call_llm(messages)
        return final_text or "✅ Done."
    
    async def stream_response(
        self,
        user_id: int,
        content: str,
        platform: str = "telegram",
        session_id: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """Stream a response token by token"""
        # For now, just yield the full response in chunks
        # Full streaming would need provider-specific handling
        response = await self.process_message(user_id, content, platform, session_id)
        
        chunk_size = 50
        for i in range(0, len(response), chunk_size):
            yield response[i:i+chunk_size]
            await asyncio.sleep(0.01)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get agent statistics"""
        return {
            "name": self.config.name,
            "version": self.config.version,
            "llm": {
                "provider": self.config.llm.provider.value,
                "model": self.config.llm.model
            },
            "memory": self.memory.get_stats(),
            "skills_count": len(self.skills.list_skills()),
            "skills_by_category": {
                cat.value: len(self.skills.list_skills(cat))
                for cat in SkillCategory
            }
        }
