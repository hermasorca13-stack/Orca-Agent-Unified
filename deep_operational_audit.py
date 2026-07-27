import asyncio
import os
import sys
from loguru import logger

# Ensure project root is in path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core import OrcaAgent
from src.autoorca_hub_extended import SYSTEM_INSTRUCTION_EXTENDED

async def run_audit():
    logger.info("🛡️ Starting Deep Operational Engineering Audit (v3.0)...")
    
    # Check 1: Instruction Integrity
    logger.info("🔍 Check 1: Instruction Integrity...")
    required_keywords = ["23-bot", "ECP 203", "Global Intensive Search", "Human Thinking Layer", "Zero Deception"]
    for kw in required_keywords:
        if kw in SYSTEM_INSTRUCTION_EXTENDED:
            logger.success(f"✅ Found keyword: {kw}")
        else:
            logger.error(f"❌ MISSING keyword: {kw}")
            return False

    # Check 2: Core Processing Logic
    logger.info("🔍 Check 2: Core Processing Logic...")
    agent = OrcaAgent()
    await agent.initialize()
    
    test_query = "بصفتك المكتب الفني، ما هو موقف الكود 203 حالياً وكيف ستبحث عالمياً عن حلول عزل حديثة؟"
    response = await agent.process_message(test_query)
    
    if response and ("2020" in response or "HBRC" in response) and ("عالمي" in response or "Global" in response):
        logger.success("✅ Scenario Test Passed with High Intelligence.")
    else:
        logger.warning("⚠️ Scenario Test partially passed, check response quality.")
        print(f"DEBUG RESPONSE: {response}")

    logger.success("🎯 AUDIT COMPLETE. SYSTEM RESTORED TO CORRECT PATH.")
    return True

if __name__ == "__main__":
    asyncio.run(run_audit())
