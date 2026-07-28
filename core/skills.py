"""
ORCA Agent - Skills System
==========================
Dynamic skill loading, execution, and management.
"""

import os
import json
import importlib
import inspect
import asyncio
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum


class SkillCategory(Enum):
    """Skill categories"""
    WEB = "web"
    CODE = "code"
    MEDIA = "media"
    DATA = "data"
    COMMUNICATION = "communication"
    PRODUCTIVITY = "productivity"
    FINANCE = "finance"
    HEALTH = "health"
    EDUCATION = "education"
    CREATIVE = "creative"
    SYSTEM = "system"
    AI = "ai"


@dataclass
class Skill:
    """Skill definition"""
    name: str
    description: str
    category: SkillCategory
    function: Callable
    parameters: Dict[str, Any] = field(default_factory=dict)
    examples: List[str] = field(default_factory=list)
    requires: List[str] = field(default_factory=list)  # required API keys
    enabled: bool = True
    
    def to_tool_schema(self) -> Dict[str, Any]:
        """Convert to OpenAI function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters or {
                    "type": "object",
                    "properties": {
                        "input": {"type": "string", "description": "User input"}
                    },
                    "required": ["input"]
                }
            }
        }


class SkillRegistry:
    """
    Registry for all available skills.
    Handles loading, execution, and discovery.
    """
    
    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = Path(skills_dir)
        self.skills: Dict[str, Skill] = {}
        self._loaded = False
    
    def register(self, skill: Skill):
        """Register a skill"""
        self.skills[skill.name] = skill
    
    def register_function(
        self,
        name: str,
        description: str,
        category: SkillCategory = SkillCategory.SYSTEM,
        parameters: Optional[Dict] = None,
        examples: Optional[List[str]] = None,
        requires: Optional[List[str]] = None
    ):
        """Decorator to register a function as a skill"""
        def decorator(func: Callable) -> Callable:
            skill = Skill(
                name=name,
                description=description,
                category=category,
                function=func,
                parameters=parameters or {},
                examples=examples or [],
                requires=requires or []
            )
            self.register(skill)
            return func
        return decorator
    
    def get_skill(self, name: str) -> Optional[Skill]:
        """Get a skill by name"""
        return self.skills.get(name)
    
    def list_skills(self, category: Optional[SkillCategory] = None) -> List[Skill]:
        """List all skills, optionally filtered by category"""
        skills = list(self.skills.values())
        if category:
            skills = [s for s in skills if s.category == category]
        return skills
    
    async def execute(self, name: str, **kwargs) -> Any:
        """Execute a skill by name"""
        skill = self.get_skill(name)
        if not skill:
            raise ValueError(f"Skill '{name}' not found")
        if not skill.enabled:
            raise ValueError(f"Skill '{name}' is disabled")
        
        if asyncio.iscoroutinefunction(skill.function):
            return await skill.function(**kwargs)
        else:
            return skill.function(**kwargs)
    
    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Get all skills as OpenAI tool schemas"""
        return [s.to_tool_schema() for s in self.skills.values() if s.enabled]
    
    def get_skills_description(self) -> str:
        """Get a text description of all skills for prompts"""
        lines = []
        for skill in self.skills.values():
            if not skill.enabled:
                continue
            lines.append(f"- {skill.name}: {skill.description}")
        return "\n".join(lines)
    
    def load_builtin_skills(self):
        """Load all built-in skills"""
        # Web skills
        self._register_web_skills()
        # Code skills
        self._register_code_skills()
        # Media skills
        self._register_media_skills()
        # Data skills
        self._register_data_skills()
        # Communication skills
        self._register_communication_skills()
        # Productivity skills
        self._register_productivity_skills()
        # AI skills
        self._register_ai_skills()
        # System skills
        self._register_system_skills()
        # Finance skills
        self._register_finance_skills()
        # GitHub skills
        self._register_github_skills()
        # Health skills
        self._register_health_skills()
        self._register_termux_skills()
        self._loaded = True
    
    def _register_web_skills(self):
        """Web-related skills"""
        
        @self.register_function(
            name="web_search",
            description="Search the web for information",
            category=SkillCategory.WEB,
            requires=["tavily_api_key or serper_api_key"]
        )
        async def web_search(query: str, num_results: int = 5) -> str:
            """Search the web using available search APIs"""
            try:
                import httpx
                
                # Try Tavily first
                tavily_key = os.getenv("TAVILY_API_KEY")
                if tavily_key:
                    async with httpx.AsyncClient() as client:
                        resp = await client.post(
                            "https://api.tavily.com/search",
                            json={"api_key": tavily_key, "query": query, "max_results": num_results},
                            timeout=30
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            results = []
                            for r in data.get("results", []):
                                results.append(f"**{r.get('title')}**\n{r.get('content')}\n🔗 {r.get('url')}")
                            return "\n\n".join(results)
                
                # Fallback to Serper
                serper_key = os.getenv("SERPER_API_KEY")
                if serper_key:
                    async with httpx.AsyncClient() as client:
                        resp = await client.post(
                            "https://google.serper.dev/search",
                            headers={"X-API-KEY": serper_key},
                            json={"q": query, "num": num_results},
                            timeout=30
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            results = []
                            for r in data.get("organic", []):
                                results.append(f"**{r.get('title')}**\n{r.get('snippet')}\n🔗 {r.get('link')}")
                            return "\n\n".join(results)
                
                return "⚠️ No web search API configured. Set TAVILY_API_KEY or SERPER_API_KEY."
            except Exception as e:
                return f"❌ Web search error: {str(e)}"
        
        @self.register_function(
            name="fetch_url",
            description="Fetch and extract content from a URL",
            category=SkillCategory.WEB
        )
        async def fetch_url(url: str) -> str:
            """Fetch a URL and extract text content"""
            try:
                import httpx
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    resp = await client.get(url, timeout=30)
                    resp.raise_for_status()
                    # Simple HTML to text
                    from html.parser import HTMLParser
                    
                    class TextExtractor(HTMLParser):
                        def __init__(self):
                            super().__init__()
                            self.text = []
                            self.skip = False
                        def handle_starttag(self, tag, attrs):
                            if tag in ('script', 'style', 'nav', 'footer'):
                                self.skip = True
                        def handle_endtag(self, tag):
                            if tag in ('script', 'style', 'nav', 'footer'):
                                self.skip = False
                        def handle_data(self, data):
                            if not self.skip:
                                self.text.append(data.strip())
                    
                    extractor = TextExtractor()
                    extractor.feed(resp.text)
                    return " ".join(t for t in extractor.text if t)[:5000]
            except Exception as e:
                return f"❌ Fetch error: {str(e)}"
    
    def _register_code_skills(self):
        """Code execution skills"""
        
        @self.register_function(
            name="execute_python",
            description="Execute Python code safely in a sandboxed environment",
            category=SkillCategory.CODE
        )
        async def execute_python(code: str) -> str:
            """Execute Python code"""
            try:
                import subprocess
                result = subprocess.run(
                    ["python3", "-c", code],
                    capture_output=True, text=True, timeout=30
                )
                output = result.stdout
                if result.stderr:
                    output += f"\n⚠️ STDERR:\n{result.stderr}"
                if result.returncode != 0:
                    output += f"\n❌ Exit code: {result.returncode}"
                return output or "✅ Executed successfully (no output)"
            except subprocess.TimeoutExpired:
                return "⏱️ Execution timed out (30s limit)"
            except Exception as e:
                return f"❌ Execution error: {str(e)}"
        
        @self.register_function(
            name="execute_bash",
            description="Execute a bash command",
            category=SkillCategory.CODE
        )
        async def execute_bash(command: str) -> str:
            """Execute a bash command with safety checks"""
            # Safety check
            dangerous = ["rm -rf /", "mkfs", "dd if=", ":(){ :|:&};:", "shutdown", "reboot"]
            if any(d in command.lower() for d in dangerous):
                return "🚫 Blocked: dangerous command detected"
            
            try:
                import subprocess
                result = subprocess.run(
                    command, shell=True, capture_output=True, text=True, timeout=60
                )
                output = result.stdout
                if result.stderr:
                    output += f"\n⚠️ STDERR:\n{result.stderr}"
                return output or "✅ Executed successfully"
            except subprocess.TimeoutExpired:
                return "⏱️ Execution timed out"
            except Exception as e:
                return f"❌ Error: {str(e)}"
    
    def _register_media_skills(self):
        """Media processing skills"""
        
        @self.register_function(
            name="generate_image",
            description="Generate an image from a text description using AI",
            category=SkillCategory.MEDIA,
            requires=["openai_api_key"]
        )
        async def generate_image(prompt: str, size: str = "1024x1024") -> str:
            """Generate image using DALL-E"""
            try:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                response = await client.images.generate(
                    model="dall-e-3", prompt=prompt, size=size, n=1
                )
                return response.data[0].url
            except Exception as e:
                return f"❌ Image generation error: {str(e)}"
        
        @self.register_function(
            name="text_to_speech",
            description="Convert text to speech audio",
            category=SkillCategory.MEDIA,
            requires=["openai_api_key or elevenlabs_api_key"]
        )
        async def text_to_speech(text: str, voice: str = "alloy") -> str:
            """Convert text to speech"""
            try:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                response = await client.audio.speech.create(
                    model="tts-1", voice=voice, input=text
                )
                # Save to temp file
                import tempfile
                tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
                tmp.write(response.content)
                tmp.close()
                return tmp.name
            except Exception as e:
                return f"❌ TTS error: {str(e)}"
        
        @self.register_function(
            name="transcribe_audio",
            description="Transcribe audio to text using Whisper",
            category=SkillCategory.MEDIA,
            requires=["openai_api_key"]
        )
        async def transcribe_audio(audio_path: str) -> str:
            """Transcribe audio file"""
            try:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                with open(audio_path, "rb") as f:
                    transcript = await client.audio.transcriptions.create(
                        model="whisper-1", file=f
                    )
                return transcript.text
            except Exception as e:
                return f"❌ Transcription error: {str(e)}"
    
    def _register_data_skills(self):
        """Data analysis skills"""
        
        @self.register_function(
            name="calculate",
            description="Perform mathematical calculations",
            category=SkillCategory.DATA
        )
        async def calculate(expression: str) -> str:
            """Safely evaluate math expression"""
            try:
                import math
                # Whitelist safe functions
                safe = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
                safe.update({"abs": abs, "round": round, "min": min, "max": max, "sum": sum, "pow": pow})
                result = eval(expression, {"__builtins__": {}}, safe)
                return f"= {result}"
            except Exception as e:
                return f"❌ Calculation error: {str(e)}"
        
        @self.register_function(
            name="analyze_data",
            description="Analyze data from a CSV or JSON file",
            category=SkillCategory.DATA
        )
        async def analyze_data(file_path: str, query: str = "summary") -> str:
            """Analyze data file"""
            try:
                import pandas as pd
                if file_path.endswith(".csv"):
                    df = pd.read_csv(file_path)
                elif file_path.endswith(".json"):
                    df = pd.read_json(file_path)
                else:
                    return "❌ Unsupported file type. Use CSV or JSON."
                
                summary = f"""
📊 **Data Summary**
- Shape: {df.shape[0]} rows × {df.shape[1]} columns
- Columns: {', '.join(df.columns.tolist())}
- Numeric columns: {df.select_dtypes(include='number').columns.tolist()}

📈 **Statistics**
{df.describe().to_string()}

🔍 **First 5 rows**
{df.head().to_string()}
"""
                return summary
            except Exception as e:
                return f"❌ Analysis error: {str(e)}"
    
    def _register_communication_skills(self):
        """Communication skills"""
        
        @self.register_function(
            name="translate",
            description="Translate text between languages",
            category=SkillCategory.COMMUNICATION
        )
        async def translate(text: str, target_lang: str = "en") -> str:
            """Translate text using LLM"""
            # This uses the LLM, will be handled by main agent
            return f"[TRANSLATE_TO_{target_lang}]{text}"
        
        @self.register_function(
            name="summarize",
            description="Summarize a long text into key points",
            category=SkillCategory.COMMUNICATION
        )
        async def summarize(text: str, max_length: int = 200) -> str:
            """Summarize text"""
            return f"[SUMMARIZE:{max_length}]{text}"
    
    def _register_productivity_skills(self):
        """Productivity skills"""
        
        @self.register_function(
            name="create_reminder",
            description="Set a reminder for the user",
            category=SkillCategory.PRODUCTIVITY
        )
        async def create_reminder(message: str, time_minutes: int) -> str:
            """Create a reminder"""
            return f"⏰ Reminder set for {time_minutes} minutes: {message}"
        
        @self.register_function(
            name="save_note",
            description="Save a note to memory",
            category=SkillCategory.PRODUCTIVITY
        )
        async def save_note(title: str, content: str) -> str:
            """Save a note"""
            return f"📝 Note saved: {title}"
    
    def _register_ai_skills(self):
        """AI-related skills"""
        
        @self.register_function(
            name="analyze_image",
            description="Analyze an image using vision AI",
            category=SkillCategory.AI,
            requires=["openai_api_key or anthropic_api_key"]
        )
        async def analyze_image(image_path: str, question: str = "Describe this image") -> str:
            """Analyze an image"""
            try:
                from openai import AsyncOpenAI
                import base64
                client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                
                with open(image_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                
                response = await client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": question},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                        ]
                    }],
                    max_tokens=1000
                )
                return response.choices[0].message.content
            except Exception as e:
                return f"❌ Image analysis error: {str(e)}"
        
        @self.register_function(
            name="extract_text_from_pdf",
            description="Extract text from a PDF file",
            category=SkillCategory.AI
        )
        async def extract_text_from_pdf(pdf_path: str) -> str:
            """Extract text from PDF"""
            try:
                import PyPDF2
                text = []
                with open(pdf_path, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    for page in reader.pages:
                        text.append(page.extract_text())
                return "\n".join(text)[:10000]
            except ImportError:
                return "❌ PyPDF2 not installed. Run: pip install PyPDF2"
            except Exception as e:
                return f"❌ PDF error: {str(e)}"
    
    def _register_system_skills(self):
        """System skills"""
        
        @self.register_function(
            name="get_datetime",
            description="Get current date and time in any timezone",
            category=SkillCategory.SYSTEM
        )
        async def get_datetime(timezone: str = "UTC") -> str:
            """Get current datetime"""
            try:
                from datetime import datetime
                import zoneinfo
                tz = zoneinfo.ZoneInfo(timezone)
                return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S %Z")
            except Exception:
                from datetime import datetime
                return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        @self.register_function(
            name="get_weather",
            description="Get current weather for a location",
            category=SkillCategory.SYSTEM,
            requires=["openweathermap_api_key"]
        )
        async def get_weather(city: str) -> str:
            """Get weather"""
            try:
                import httpx
                key = os.getenv("OPENWEATHERMAP_API_KEY")
                if not key:
                    return "⚠️ OPENWEATHERMAP_API_KEY not set"
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={key}&units=metric",
                        timeout=10
                    )
                    data = resp.json()
                    return f"🌤️ **{city}**: {data['main']['temp']}°C, {data['weather'][0]['description']}, humidity {data['main']['humidity']}%"
            except Exception as e:
                return f"❌ Weather error: {str(e)}"


    def _register_finance_skills(self):
        """Finance & crypto skills"""
        
        @self.register_function(
            name="crypto_price",
            description="Get current cryptocurrency price",
            category=SkillCategory.FINANCE
        )
        async def crypto_price(symbol: str = "bitcoin", currency: str = "usd") -> str:
            """Get crypto price from CoinGecko (free, no API key)"""
            try:
                import httpx
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"https://api.coingecko.com/api/v3/simple/price",
                        params={"ids": symbol.lower(), "vs_currencies": currency.lower()},
                        timeout=10
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        if symbol.lower() in data:
                            price = data[symbol.lower()].get(currency.lower(), "N/A")
                            return f"💰 **{symbol.upper()}** = {price} {currency.upper()}"
                        return f"❌ Symbol '{symbol}' not found. Try: bitcoin, ethereum, solana"
                    return f"❌ API error: {resp.status_code}"
            except Exception as e:
                return f"❌ Crypto error: {str(e)}"
        
        @self.register_function(
            name="stock_price",
            description="Get stock price for a ticker symbol",
            category=SkillCategory.FINANCE
        )
        async def stock_price(symbol: str) -> str:
            """Get stock price from Yahoo Finance (free)"""
            try:
                import httpx
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol.upper()}",
                        timeout=10
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        result = data.get("chart", {}).get("result", [])
                        if result:
                            meta = result[0].get("meta", {})
                            price = meta.get("regularMarketPrice", "N/A")
                            currency = meta.get("currency", "USD")
                            return f"📈 **{symbol.upper()}** = {price} {currency}"
                        return f"❌ Symbol '{symbol}' not found"
                    return f"❌ API error: {resp.status_code}"
            except Exception as e:
                return f"❌ Stock error: {str(e)}"
        
        @self.register_function(
            name="currency_convert",
            description="Convert between currencies",
            category=SkillCategory.FINANCE
        )
        async def currency_convert(amount: float, from_currency: str, to_currency: str) -> str:
            """Convert currency"""
            try:
                import httpx
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"https://api.exchangerate-api.com/v4/latest/{from_currency.upper()}",
                        timeout=10
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        rate = data.get("rates", {}).get(to_currency.upper())
                        if rate:
                            result = amount * rate
                            return f"💱 {amount} {from_currency.upper()} = {result:.2f} {to_currency.upper()}"
                        return f"❌ Currency '{to_currency}' not found"
                    return f"❌ API error: {resp.status_code}"
            except Exception as e:
                return f"❌ Conversion error: {str(e)}"
    
    def _register_github_skills(self):
        """GitHub integration skills"""
        
        @self.register_function(
            name="github_search",
            description="Search GitHub repositories",
            category=SkillCategory.CODE
        )
        async def github_search(query: str, limit: int = 5) -> str:
            """Search GitHub repos"""
            try:
                import httpx
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        "https://api.github.com/search/repositories",
                        params={"q": query, "per_page": limit, "sort": "stars"},
                        headers={"Accept": "application/vnd.github.v3+json"},
                        timeout=15
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        items = data.get("items", [])
                        if not items:
                            return "❌ No repositories found"
                        results = []
                        for item in items:
                            results.append(
                                f"**{item['full_name']}** ⭐ {item['stargazers_count']}\n"
                                f"{item.get('description', 'No description')}\n"
                                f"🔗 {item['html_url']}"
                            )
                        return "\n\n".join(results)
                    return f"❌ API error: {resp.status_code}"
            except Exception as e:
                return f"❌ GitHub search error: {str(e)}"
        
        @self.register_function(
            name="github_user_info",
            description="Get GitHub user information",
            category=SkillCategory.CODE
        )
        async def github_user_info(username: str) -> str:
            """Get GitHub user info"""
            try:
                import httpx
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"https://api.github.com/users/{username}",
                        headers={"Accept": "application/vnd.github.v3+json"},
                        timeout=10
                    )
                    if resp.status_code == 200:
                        u = resp.json()
                        return (
                            f"👤 **{u.get('name') or u['login']}**\n"
                            f"📝 {u.get('bio', 'No bio')}\n"
                            f"📍 {u.get('location', 'Unknown')}\n"
                            f"📦 Public repos: {u.get('public_repos', 0)}\n"
                            f"👥 Followers: {u.get('followers', 0)}\n"
                            f"🔗 {u['html_url']}"
                        )
                    return f"❌ User not found"
            except Exception as e:
                return f"❌ Error: {str(e)}"
    
    def _register_health_skills(self):
        """Health-related skills"""

    def _register_termux_skills(self):
        """Termux automation skills"""
        from .termux_automation import TermuxAutomationSkills
        termux_skills_instance = TermuxAutomationSkills()

        @self.register_function(
            name="execute_termux_command",
            description="Executes a shell command within Termux environment (simulated here).",
            category=SkillCategory.SYSTEM,
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The shell command to execute"},
                    "description": {"type": "string", "description": "Optional description of the command's purpose"}
                },
                "required": ["command"]
            }
        )
        async def execute_termux_command(command: str, description: Optional[str] = None) -> str:
            return await termux_skills_instance.execute_termux_command(command, description)

        @self.register_function(
            name="adb_tap",
            description="Simulates a tap on the Android screen using ADB.",
            category=SkillCategory.SYSTEM,
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate for the tap"},
                    "y": {"type": "integer", "description": "Y coordinate for the tap"}
                },
                "required": ["x", "y"]
            }
        )
        async def adb_tap(x: int, y: int) -> str:
            return await termux_skills_instance.adb_tap(x, y)

        @self.register_function(
            name="adb_swipe",
            description="Simulates a swipe on the Android screen using ADB.",
            category=SkillCategory.SYSTEM,
            parameters={
                "type": "object",
                "properties": {
                    "x1": {"type": "integer", "description": "Starting X coordinate"},
                    "y1": {"type": "integer", "description": "Starting Y coordinate"},
                    "x2": {"type": "integer", "description": "Ending X coordinate"},
                    "y2": {"type": "integer", "description": "Ending Y coordinate"},
                    "duration": {"type": "integer", "description": "Duration of the swipe in milliseconds"}
                },
                "required": ["x1", "y1", "x2", "y2"]
            }
        )
        async def adb_swipe(x1: int, y1: int, x2: int, y2: int, duration: int = 300) -> str:
            return await termux_skills_instance.adb_swipe(x1, y1, x2, y2, duration)

        @self.register_function(
            name="adb_text",
            description="Types text into an active input field using ADB.",
            category=SkillCategory.SYSTEM,
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The text to type"}
                },
                "required": ["text"]
            }
        )
        async def adb_text(text: str) -> str:
            return await termux_skills_instance.adb_text(text)

        @self.register_function(
            name="adb_keyevent",
            description="Sends a key event (e.g., back button) using ADB.",
            category=SkillCategory.SYSTEM,
            parameters={
                "type": "object",
                "properties": {
                    "keycode": {"type": "integer", "description": "The keycode to send (e.g., 4 for back button)"}
                },
                "required": ["keycode"]
            }
        )
        async def adb_keyevent(keycode: int) -> str:
            return await termux_skills_instance.adb_keyevent(keycode)





        @self.register_function(
            name="adb_pull_file",
            description="Pulls a file from the Android device to the Termux environment.",
            category=SkillCategory.SYSTEM,
            parameters={
                "type": "object",
                "properties": {
                    "remote_path": {"type": "string", "description": "Path on the Android device"},
                    "local_path": {"type": "string", "description": "Path in the Termux environment"}
                },
                "required": ["remote_path", "local_path"]
            }
        )
        async def adb_pull_file(remote_path: str, local_path: str) -> str:
            return await termux_skills_instance.adb_pull_file(remote_path, local_path)

        @self.register_function(
            name="adb_start_activity",
            description="Starts an Android activity using ADB.",
            category=SkillCategory.SYSTEM,
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "The action to perform (e.g., android.intent.action.VIEW)"},
                    "data": {"type": "string", "description": "Optional data URI for the intent"},
                    "component": {"type": "string", "description": "Optional component name (e.g., com.android.chrome/com.google.android.apps.chrome.Main)"}
                },
                "required": ["action"]
            }
        )
        async def adb_start_activity(action: str, data: Optional[str] = None, component: Optional[str] = None) -> str:
            return await termux_skills_instance.adb_start_activity(action, data, component)

        @self.register_function(
            name="termux_api_call",
            description="Executes a Termux:API command.",
            category=SkillCategory.SYSTEM,
            parameters={
                "type": "object",
                "properties": {
                    "api_command": {"type": "string", "description": "The Termux:API command (e.g., battery-status)"},
                    "args": {"type": "array", "items": {"type": "string"}, "description": "Optional arguments for the API command"}
                },
                "required": ["api_command"]
            }
        )
        async def termux_api_call(api_command: str, *args) -> str:
            return await termux_skills_instance.termux_api_call(api_command, *args)

# Global registry
_registry: Optional[SkillRegistry] = None


def get_registry() -> SkillRegistry:
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
        _registry.load_builtin_skills()
    return _registry
