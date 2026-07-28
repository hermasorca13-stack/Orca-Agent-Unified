# core/config.py - Orca Agent Unified Config Loader
"""
Single source of truth for runtime configuration.
Exposes both:
  - v2 interface: `config` (Config instance) - used by orca.py, telegram_bot, api_manager, github_sync
  - legacy interface: `OrcaConfig` + `get_config()` - used by core/agent.py, core/memory.py, platforms/telegram.py
This dual export avoids breaking any of the v2 kernel modules while keeping backward compatibility.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


# ----------------------------------------------------------------------
# v2 flat config (used by orca.py / telegram_bot / api_manager / etc.)
# ----------------------------------------------------------------------
class Config:
    # Telegram
    TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    TG_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "HermesOrcaXBot").strip()
    TG_CLIENT_ID = os.getenv("TELEGRAM_CLIENT_ID", "").strip()
    TG_CLIENT_SECRET = os.getenv("TELEGRAM_CLIENT_SECRET", "").strip()
    TG_BOT_HASH = os.getenv("TELEGRAM_BOT_HASH", "").strip()

    # GitHub
    GH_USER = os.getenv("GITHUB_USERNAME", "hermasorca13").strip()
    GH_EMAIL = os.getenv("GITHUB_EMAIL", "hermasorca13@gmail.com").strip()
    GH_REPO = os.getenv("GITHUB_REPO", "Orca-Agent-Unified").strip()
    GH_BRANCH = os.getenv("GITHUB_BRANCH", "master").strip()
    GH_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()

    # Orca Master
    ORCA_MASTER = os.getenv("ORCA_MASTER_TOKEN", "").strip()
    ORCA_UNIVERSAL = os.getenv("ORCA_UNIVERSAL_KEY", "").strip()

    # Android bridge
    ADB_HOST = os.getenv("ANDROID_ADB_HOST", "127.0.0.1").strip()
    ADB_PORT = int(os.getenv("ANDROID_ADB_PORT", "5037"))
    ADB_SERIAL = os.getenv("ANDROID_DEVICE_SERIAL", "auto").strip()

    # LLM (legacy aliases consumed by core/agent.py)
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
    LLM_MODEL = os.getenv("LLM_MODEL", "claude-3-5-sonnet-20241022").strip()
    LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY") or os.getenv("OPENAI_API_KEY", "").strip()
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").strip() or None

    # Memory
    MEMORY_DB_PATH = os.getenv("MEMORY_DB_PATH", str(ROOT / "data" / "memory.db"))
    MEMORY_MAX_CONTEXT = int(os.getenv("MEMORY_MAX_CONTEXT", "20"))

    # Paths
    ROOT = ROOT
    LOG_PATH = ROOT / "logs" / "orca.log"
    DATA_PATH = ROOT / "data"
    BACKUP_PATH = ROOT / "backups"
    SKILLS_PATH = ROOT / "skills"
    SKILLS_DATA_PATH = ROOT / "core" / "skills_data"

    # Mode
    RUN_MODE = os.getenv("RUN_MODE", "production").strip()
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").strip().upper()

    @classmethod
    def validate(cls):
        missing = []
        if not cls.TG_TOKEN:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not cls.GH_USER:
            missing.append("GITHUB_USERNAME")
        if not cls.ORCA_MASTER:
            missing.append("ORCA_MASTER_TOKEN")
        if missing:
            logger.warning(f"Missing env: {missing}")
            return False
        logger.info(f"Config validated | Bot: @{cls.TG_USERNAME} | Repo: {cls.GH_REPO}")
        return True


# ----------------------------------------------------------------------
# Legacy structured config (consumed by core/agent.py + platforms/telegram.py)
# ----------------------------------------------------------------------
class _TelegramPlatformConfig:
    def __init__(self, token: str = "", allowed_users=None):
        self.token = token
        self.allowed_users = allowed_users or []


class _LLMProvider:
    def __init__(self, name: str):
        self.value = name


class _LLMConfig:
    def __init__(self):
        self.provider = _LLMProvider(Config.LLM_PROVIDER)
        self.model = Config.LLM_MODEL
        self.api_key = Config.LLM_API_KEY
        self.base_url = Config.LLM_BASE_URL


class _MemoryConfig:
    def __init__(self):
        self.db_path = Config.MEMORY_DB_PATH
        self.max_context_length = Config.MEMORY_MAX_CONTEXT


class OrcaConfig:
    """Legacy structured config consumed by core/agent.py, core/memory.py, platforms/telegram.py."""
    def __init__(self):
        self.telegram_token = Config.TG_TOKEN
        self.llm = _LLMConfig()
        self.memory = _MemoryConfig()
        self.platforms_dict = {
            "telegram": _TelegramPlatformConfig(
                token=Config.TG_TOKEN,
                allowed_users=[],
            )
        }

    @property
    def platforms(self):
        return self.platforms_dict

    def get(self, key, default=None):
        return getattr(self, key, default)


_cached_config: "OrcaConfig | None" = None


def get_config() -> OrcaConfig:
    """Return the singleton OrcaConfig (legacy interface)."""
    global _cached_config
    if _cached_config is None:
        _cached_config = OrcaConfig()
    return _cached_config


# ----------------------------------------------------------------------
# Module-level singletons
# ----------------------------------------------------------------------
config = Config()          # v2 flat singleton
orca_config = get_config() # legacy structured singleton
