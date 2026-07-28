import os
import asyncio
from loguru import logger
from core.autoorca_hub_extended import AUTOORCA_CONFIG
from core.skills_integration import injector

class OrcaComprehensiveTest:
    def __init__(self):
        self.results = {}

    async def test_engineering_logic(self):
        logger.info("🧪 Testing Role 20: ECP 203 Conflict Resolution...")
        evidence = AUTOORCA_CONFIG["ENGINEERING_EXTENSIONS"]["FIELD_EVIDENCE"]["ECP_203_STATUS"]
        if "2020" in evidence and "HBRC" in evidence:
            self.results["Engineering Logic"] = "✅ PASSED: Correctly identifies ECP 203 status."
        else:
            self.results["Engineering Logic"] = "❌ FAILED: Evidence missing or incorrect."

    async def test_human_thinking_layer(self):
        logger.info("🧪 Testing Human Thinking Layer...")
        layer = AUTOORCA_CONFIG["ENGINEERING_EXTENSIONS"]["HUMAN_LAYER"]
        if "فحص حدسي" in layer and "موازنة الكودي مقابل الواقعي" in layer:
            self.results["Human Thinking Layer"] = "✅ PASSED: Human-like reasoning logic is active."
        else:
            self.results["Human Thinking Layer"] = "❌ FAILED: Thinking layer not properly injected."

    async def test_skills_availability(self):
        logger.info("🧪 Testing Injected Skills Availability...")
        skills = injector.load_skills()
        required = ['skill_creator', 'manus_api', 'youtube_research', 'video_generator']
        missing = [s for s in required if s not in skills]
        if not missing:
            self.results["Skills Integration"] = "✅ PASSED: All 4 skills are ready for execution."
        else:
            self.results["Skills Integration"] = f"❌ FAILED: Missing skills: {missing}"

    async def run_all(self):
        await self.test_engineering_logic()
        await self.test_human_thinking_layer()
        await self.test_skills_availability()
        
        print("\n" + "="*40)
        print("🚀 ORCA AGENT COMPREHENSIVE TEST RESULTS")
        print("="*40)
        for test, res in self.results.items():
            print(f"{test}: {res}")
        print("="*40 + "\n")

if __name__ == "__main__":
    tester = OrcaComprehensiveTest()
    asyncio.run(tester.run_all())
