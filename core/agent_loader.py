"""
core/agent_loader.py
====================
Bridges OrcaAgent (LLM + memory + skills registry) into the rest of the system.

This module is an *addition*. It does not modify core/agent.py or core/skills.py.
It only:
  1. Imports OrcaAgent (already complete) and instantiates it.
  2. Triggers load_builtin_skills() to register the 25+ built-in skills.
  3. Optionally loads any extra "src/" skills that export a register(registry) function.
  4. Exposes a process() helper used by telegram_bot/bot.py when LLM is configured.

If no LLM API key is present, process() returns None so callers can fall back.
"""
from __future__ import annotations
import os
import sys
import asyncio
import importlib
import importlib.util
from pathlib import Path
from typing import Optional, Any, Dict, List

from loguru import logger

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from core.config import config  # type: ignore
except Exception:
    config = None  # type: ignore


class AgentBridge:
    """Single, lazy-loaded bridge to OrcaAgent + SkillRegistry."""

    _instance: Optional["AgentBridge"] = None
    _agent = None
    _registry = None
    _ready = False
    _reason: str = ""

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def initialize(self) -> bool:
        """Try to bring OrcaAgent + SkillRegistry online. Safe to call repeatedly.

        Behaviour:
          - If LLM key is present: full OrcaAgent + 25+ skills (real LLM).
          - If LLM key is absent: still ready, but in "rule-based" mode using
            the local skill registry (so the bot stays useful offline).
        """
        if self._ready:
            return True
        try:
            from core.skills import get_registry
            self._registry = get_registry()
            try:
                self._registry.load_builtin_skills()
                logger.info(f"SkillRegistry loaded built-in skills: {len(self._registry.list_skills())}")
            except Exception as e:
                logger.warning(f"load_builtin_skills issue: {e}")
            try:
                self._load_src_skills()
            except Exception as e:
                logger.debug(f"src/ skills scan skipped: {e}")
        except Exception as e:
            logger.warning(f"SkillRegistry unavailable: {e}")

        llm_key = (getattr(config, "LLM_API_KEY", "") if config else "").strip()
        if llm_key:
            try:
                from core.agent import OrcaAgent
                self._agent = OrcaAgent()
                if getattr(self._agent, "_llm_client", None) is not None:
                    self._ready = True
                    self._reason = "llm"
                    logger.success("AgentBridge ready (OrcaAgent + LLM)")
                    return True
                logger.info("OrcaAgent constructed but no _llm_client — falling back to rule-based")
            except Exception as e:
                logger.warning(f"OrcaAgent init failed: {e} — falling back to rule-based")

        # Rule-based fallback (still useful, uses skill registry for tool calls)
        self._ready = True
        self._reason = "rule-based (no LLM key)"
        logger.info("AgentBridge ready in rule-based mode")
        return True

    def _load_src_skills(self) -> int:
        """Scan src/ for modules exposing register(registry) -> None."""
        if not self._registry:
            return 0
        src_dir = _ROOT / "src"
        if not src_dir.is_dir():
            return 0
        loaded = 0
        for py in sorted(src_dir.glob("*.py")):
            if py.name == "__init__.py" or py.name.startswith("_"):
                continue
            mod_name = f"src_extra_{py.stem}"
            spec = importlib.util.spec_from_file_location(mod_name, py)
            if not spec or not spec.loader:
                continue
            try:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                reg = getattr(mod, "register", None)
                if callable(reg):
                    reg(self._registry)
                    loaded += 1
                    logger.info(f"Registered src skill: {py.stem}")
            except Exception as e:
                logger.debug(f"src/{py.name} not a skill module: {e}")
        return loaded

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def reason(self) -> str:
        return self._reason

    def list_skills(self) -> List[str]:
        if not self._registry:
            return []
        return [s.name for s in self._registry.list_skills()]

    async def process(self, user_id: int, text: str, platform: str = "telegram",
                      metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Run a response. Uses OrcaAgent if LLM is available, otherwise rule-based."""
        if not self._ready and not self.initialize():
            return None
        # 1) Real LLM path
        if self._agent is not None and getattr(self._agent, "_llm_client", None) is not None:
            try:
                return await self._agent.process_message(
                    user_id=user_id,
                    content=text,
                    platform=platform,
                    metadata=metadata or {},
                )
            except Exception as e:
                logger.exception("OrcaAgent.process_message failed, falling back to rule-based")
        # 2) Rule-based fallback — still useful, uses skill registry
        return self._rule_based(text, user_id, metadata or {})

    def _rule_based(self, text: str, user_id: int, metadata: Dict[str, Any]) -> str:
        """A small but useful intent router: time, echo, skill listing, help, status."""
        t = (text or "").strip()
        low = t.lower()
        from datetime import datetime
        if not t:
            return "👋 Send me anything. Try: `time`, `skills`, `status`, `help`."
        if low in {"hi", "hello", "hey", "اهلا", "أهلا", "السلام"}:
            return (
                f"👋 Hi! I'm Orca (rule-based mode, no LLM key yet).\n"
                f"Try: time, skills, status, help, or just chat.\n"
                f"Set LLM_API_KEY or OPENAI_API_KEY in .env to unlock full brain."
            )
        if "time" in low or "الساعة" in t or "الوقت" in t:
            return f"🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        if "skills" in low or "مهارات" in t or "المهارات" in t:
            skills = self.list_skills()
            return f"🧠 {len(skills)} skills available:\n" + "\n".join(f"• {s}" for s in skills[:30])
        if "help" in low or "مساعدة" in t:
            return (
                "ℹ️ Orca help:\n"
                "• time — current time\n"
                "• skills — list registered skills\n"
                "• status — bridge status\n"
                "• /sync, /exec, /device, /token — bot commands\n"
                "Set LLM_API_KEY for full conversational AI."
            )
        if "status" in low:
            return f"📊 Bridge: ready=True mode={self._reason} skills={len(self.list_skills())}"
        # Echo
        return f"🤖 (rule-based) You said: {t[:400]}\n(Add LLM_API_KEY to .env for real AI responses.)"

    def memory_stats(self) -> Dict[str, Any]:
        try:
            mem = getattr(self._agent, "memory", None) if self._agent else None
            if mem and hasattr(mem, "get_stats"):
                return mem.get_stats()
        except Exception:
            pass
        return {}


bridge = AgentBridge()
