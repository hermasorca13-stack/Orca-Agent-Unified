import os
from loguru import logger
import base64

class SensoryPerceptionUpgrade:
    def __init__(self):
        # Lazy init: only create OpenAI client when an api_key is available.
        self.client = None
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
        if api_key:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=api_key)
                logger.info("SensoryPerceptionUpgrade: OpenAI client ready")
            except Exception as e:
                logger.warning(f"SensoryPerceptionUpgrade: OpenAI init failed: {e}")
        else:
            logger.debug("SensoryPerceptionUpgrade: no key — offline mode")

    async def analyze_image(self, image_path, prompt="اشرح محتوى هذه الصورة الهندسية بالتفصيل"):
        if not self.client:
            return f"[SensoryPerception offline] Set OPENAI_API_KEY in .env to enable vision analysis. Image: {image_path}"
        try:
            with open(image_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                            }
                        ]
                    }
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"❌ Vision Analysis Error: {e}")
            return f"فشلت في تحليل الصورة. الخطأ: {e}"

sensory_upgrade = SensoryPerceptionUpgrade()
