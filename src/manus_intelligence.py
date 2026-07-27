import os
from openai import OpenAI
from loguru import logger

class ManusIntelligence:
    def __init__(self):
        self.client = OpenAI()
        # Verified models available in this environment
        self.models = ["gpt-5-mini", "gpt-4.1-mini", "claude-sonnet-4-6"]

    async def get_response(self, prompt, system_prompt=""):
        for model in self.models:
            try:
                logger.info(f"🧠 Attempting Global Intelligence with {model}...")
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.7
                )
                if response and response.choices and len(response.choices) > 0:
                    content = response.choices[0].message.content
                    if content:
                        logger.success(f"✅ Response received from {model}")
                        return content
            except Exception as e:
                logger.warning(f"⚠️ Model {model} failed: {e}")
                continue
        
        return "عذراً يا هندسة، واجهت مشكلة في الاتصال بمحركات الذكاء العالمية. يرجى المحاولة بعد لحظات."

manus_intel = ManusIntelligence()
