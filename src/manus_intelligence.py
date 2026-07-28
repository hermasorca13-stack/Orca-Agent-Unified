import os
from loguru import logger

class ManusIntelligence:
    def __init__(self):
        # Lazy init — only create OpenAI client when an api_key is actually available.
        # This keeps the module importable in offline / rule-based mode (no LLM key).
        self.client = None
        self.models = ["gpt-5-mini", "gpt-4.1-mini", "claude-sonnet-4-6"]
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
        if api_key:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=api_key)
                logger.info("ManusIntelligence: OpenAI client ready")
            except Exception as e:
                logger.warning(f"ManusIntelligence: OpenAI init failed: {e}")
        else:
            logger.debug("ManusIntelligence: no OPENAI_API_KEY — falling back to rule-based")

    async def get_response(self, prompt, system_prompt=""):
        if not self.client:
            return ("[ManusIntelligence offline] Set OPENAI_API_KEY in .env to enable. "
                    f"Got prompt ({len(prompt)} chars): {prompt[:120]}…")
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
