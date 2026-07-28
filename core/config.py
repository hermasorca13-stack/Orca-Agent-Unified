"""
ORCA Agent - Configuration Module
==================================
Central configuration management with environment variable support,
validation, and type safety.
"""

import os
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field, asdict
from enum import Enum


class LLMProvider(Enum):
    """Supported LLM providers"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    GOOGLE = "google"
    OPENROUTER = "openrouter"
    LOCAL = "local"


class PlatformType(Enum):
    """Supported messaging platforms"""
    TELEGRAM = "telegram"
    DISCORD = "discord"
    SLACK = "slack"
    WHATSAPP = "whatsapp"
    SIGNAL = "signal"
    EMAIL = "email"


@dataclass
class LLMConfig:
    """LLM configuration"""
    provider: LLMProvider = LLMProvider.OPENAI
    model: str = "gpt-4o"
    api_key: str = ""
    base_url: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: int = 60
    max_retries: int = 3


@dataclass
class MemoryConfig:
    """Memory system configuration"""
    backend: str = "sqlite"  # sqlite, redis, postgres
    db_path: str = "data/memory.db"
    max_context_length: int = 128000
    compression_threshold: float = 0.8
    retention_days: int = 90
    enable_semantic_search: bool = True
    vector_dim: int = 1536


@dataclass
class PlatformConfig:
    """Messaging platform configuration"""
    enabled: bool = True
    token: str = ""
    allowed_users: List[int] = field(default_factory=list)
    admin_users: List[int] = field(default_factory=list)
    webhook_url: Optional[str] = None
    rate_limit_per_minute: int = 30


@dataclass
class SkillsConfig:
    """Skills system configuration"""
    enabled_skills: List[str] = field(default_factory=list)
    auto_load: bool = True
    skills_dir: str = "skills"
    max_skill_execution_time: int = 300


@dataclass
class SecurityConfig:
    """Security configuration"""
    enable_sandbox: bool = True
    sandbox_type: str = "docker"  # docker, subprocess, restricted
    max_file_size_mb: int = 100
    allowed_file_types: List[str] = field(default_factory=lambda: [
        ".txt", ".pdf", ".docx", ".xlsx", ".png", ".jpg", ".jpeg", ".gif", ".mp3", ".wav", ".mp4"
    ])
    blocked_commands: List[str] = field(default_factory=lambda: [
        "rm -rf /", "mkfs", "dd if=", ":(){:|:&};:", "shutdown", "reboot"
    ])
    encrypt_at_rest: bool = True


@dataclass
class LoggingConfig:
    """Logging configuration"""
    level: str = "INFO"
    log_to_file: bool = True
    log_file: str = "logs/orca.log"
    max_log_size_mb: int = 50
    backup_count: int = 5
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


@dataclass
class TermuxConfig:
    """Termux configuration"""
    enabled: bool = True
    adb_host: str = "localhost"
    adb_port: int = 5555

@dataclass
class OrcaConfig:
    """Main ORCA configuration"""
    name: str = "ORCA"
    version: str = "1.0.0"
    environment: str = "production"  # development, staging, production
    debug: bool = False
    llm: LLMConfig = field(default_factory=LLMConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    platforms: Dict[str, PlatformConfig] = field(default_factory=dict)
    skills: SkillsConfig = field(default_factory=SkillsConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    termux: TermuxConfig = field(default_factory=TermuxConfig)
    universal_api_key: str = ""
    
    def __post_init__(self):
        """Initialize default platform configs if not provided"""
        if not self.platforms:
            self.platforms = {
                "telegram": PlatformConfig(
                    enabled=True,
                    token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
                    allowed_users=self._parse_user_list(os.getenv("TELEGRAM_ALLOWED_USERS", "")),
                    admin_users=self._parse_user_list(os.getenv("TELEGRAM_ADMIN_USERS", ""))
                )
            }
    
    @staticmethod
    def _parse_user_list(value: str) -> List[int]:
        """Parse comma-separated user IDs"""
        if not value:
            return []
        try:
            return [int(uid.strip()) for uid in value.split(",") if uid.strip()]
        except ValueError:
            return []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary"""
        return asdict(self)
    
    def save(self, path: str = "data/config.json"):
        """Save config to file"""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False, default=str)
    
    @classmethod
    def from_env(cls) -> "OrcaConfig":
        """Create config from environment variables"""
        config = cls()
        
        # LLM from env
        if api_key := os.getenv("OPENAI_API_KEY"):
            config.llm.provider = LLMProvider.OPENAI
            config.llm.api_key = api_key
            config.llm.model = os.getenv("OPENAI_MODEL", "gpt-4o")
        elif api_key := os.getenv("ANTHROPIC_API_KEY"):
            config.llm.provider = LLMProvider.ANTHROPIC
            config.llm.api_key = api_key
            config.llm.model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
        elif api_key := os.getenv("DEEPSEEK_API_KEY"):
            config.llm.provider = LLMProvider.DEEPSEEK
            config.llm.api_key = api_key
            config.llm.model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
            config.llm.base_url = "https://api.deepseek.com/v1"
        elif api_key := os.getenv("OPENROUTER_API_KEY"):
            config.llm.provider = LLMProvider.OPENROUTER
            config.llm.api_key = api_key
            config.llm.base_url = "https://openrouter.ai/api/v1"
            config.llm.model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o")
        
        config.environment = os.getenv("ORCA_ENV", "production")
        config.debug = os.getenv("ORCA_DEBUG", "false").lower() == "true"
        
        # Load Universal API Key if exists
        config.universal_api_key = os.getenv("ORCA_UNIVERSAL_API_KEY", "")
        
        return config


def get_config() -> OrcaConfig:
    """Get or create the global configuration"""
    global _config
    if _config is None:
        _config = OrcaConfig.from_env()
    return _config


def reload_config() -> OrcaConfig:
    """Reload configuration from environment"""
    global _config
    _config = OrcaConfig.from_env()
    return _config


# Global config instance
_config: Optional[OrcaConfig] = None
