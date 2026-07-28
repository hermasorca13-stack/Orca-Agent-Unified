import os
import asyncio
from loguru import logger
from .manus_intelligence import manus_intel
from core.autoorca_hub_extended import SYSTEM_INSTRUCTION_EXTENDED

class OrcaAgent:
    def __init__(self):
        self.is_initialized = False
        logger.info("🦅 Orca Agent Core - Rebuilding for Maximum Stability...")

    async def initialize(self):
        self.is_initialized = True
        logger.success("✅ Core Initialized.")
        return True

    async def process_message(self, prompt, user_id=None):
        """Standard interface for all interactions."""
        try:
            logger.info(f"📥 Processing: {prompt[:50]}...")
            system_context = SYSTEM_INSTRUCTION_EXTENDED
            response = await manus_intel.get_response(prompt, system_prompt=system_context)
            return response
        except Exception as e:
            logger.error(f"❌ Core Error: {e}")
            return f"عذراً يا هندسة، واجهت مشكلة تقنية. الخطأ: {str(e)}"

    async def chat(self, prompt):
        """Legacy compatibility for chat attribute."""
        return await self.process_message(prompt)

    async def handle_image(self, image_path, prompt=None):
        from .sensory_perception_upgrade import sensory_upgrade
        return await sensory_upgrade.analyze_image(image_path, prompt)

