import os
from openai import OpenAI
from loguru import logger
import base64

class SensoryPerceptionUpgrade:
    def __init__(self):
        self.client = OpenAI()

    async def analyze_image(self, image_path, prompt="اشرح محتوى هذه الصورة الهندسية بالتفصيل"):
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
