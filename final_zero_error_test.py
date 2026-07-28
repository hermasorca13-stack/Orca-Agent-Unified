import asyncio
import os
import sys
from loguru import logger

# Ensure project root is in path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core import OrcaAgent

async def run_protocol():
    logger.info("🛡️ Starting Zero-Error Engineering Protocol...")
    agent = OrcaAgent()
    await agent.initialize()
    
    # Scenario 1: Normal Engineering Query
    logger.info("🧪 Scenario 1: Normal Engineering Query")
    response = await agent.process_message("ما هي اشتراطات الغطاء الخرساني في الكود 203؟")
    if response and "الغطاء" in response:
        logger.success("✅ Scenario 1 Passed.")
    else:
        logger.error("❌ Scenario 1 Failed.")
        return False

    # Scenario 2: Legacy 'chat' attribute check
    logger.info("🧪 Scenario 2: Legacy 'chat' attribute check")
    if hasattr(agent, 'chat'):
        response = await agent.chat("اختبار التوافق")
        logger.success("✅ Scenario 2 Passed.")
    else:
        logger.error("❌ Scenario 2 Failed: No 'chat' attribute.")
        return False

    logger.success("🎯 ALL SCENARIOS PASSED. SYSTEM STABLE.")
    return True

if __name__ == "__main__":
    if asyncio.run(run_protocol()):
        sys.exit(0)
    else:
        sys.exit(1)
