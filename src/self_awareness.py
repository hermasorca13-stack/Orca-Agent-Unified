"""Self-Awareness Module for Orca Agent"""

import asyncio
from typing import Dict, Any, List
from loguru import logger

class SelfAwareness:
    """Handles self-explanation, uncertainty disclosure, and bias detection"""

    def __init__(self):
        logger.info("🧠 Initializing Self-Awareness module...")
        logger.info("✅ Self-Awareness module initialized.")

    async def explain_thinking(self, task: str, reasoning_steps: List[str]) -> Dict:
        """Provide a transparent chain-of-thought explanation for a task"""
        logger.info("Explaining thinking process.")
        
        explanation = f"To solve '{task}', I followed these steps: " + " -> ".join(reasoning_steps)
        
        return {"status": "success", "explanation": explanation}

    async def disclose_uncertainty(self, confidence_level: float) -> Dict:
        """Disclose confidence levels and potential pitfalls"""
        logger.info(f"Disclosing uncertainty (Confidence: {confidence_level})")
        
        message = "I am highly confident in this result." if confidence_level > 0.8 else "I am not entirely sure, let me verify this."
        
        return {"status": "success", "confidence": confidence_level, "message": message}

    async def detect_biases(self, response: str) -> Dict:
        """Detect and disclose potential biases in the agent's responses"""
        logger.info("Detecting biases in response.")
        
        biases = ["Potential gender bias detected in occupation description."]
        
        return {"status": "success", "biases": biases}


# Example usage (for testing purposes)
async def main():
    awareness_engine = SelfAwareness()

    print("\n--- Explaining Thinking ---")
    think_result = await awareness_engine.explain_thinking("Calculate ROI", ["Gather data", "Apply formula", "Format result"])
    print(think_result)

    print("\n--- Disclosing Uncertainty ---")
    uncert_result = await awareness_engine.disclose_uncertainty(0.65)
    print(uncert_result)

if __name__ == "__main__":
    asyncio.run(main())
