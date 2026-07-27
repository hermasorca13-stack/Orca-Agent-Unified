import asyncio
import os
import sys
# Ensure project root is in path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core import OrcaAgent

async def test_global_intelligence():
    print("🧪 Running Internal Engineering Test (Global Intelligence)...")
    agent = OrcaAgent()
    await agent.initialize()
    
    test_query = "اشرح لي باختصار أهمية الكود 203 في الهندسة الإنشائية وما هو دورك في مساعدتي؟"
    response = await agent.process_message(test_query)
    
    print("\n" + "="*50)
    print("🤖 AGENT RESPONSE:")
    print(response)
    print("="*50 + "\n")
    
    if "203" in response and "هندسة" in response:
        print("✅ TEST PASSED: Response is intelligent and engineering-focused.")
    else:
        print("❌ TEST FAILED: Response did not meet engineering standards.")

if __name__ == "__main__":
    asyncio.run(test_global_intelligence())
