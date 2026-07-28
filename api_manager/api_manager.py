# api_manager/api_manager.py - Universal API Token Manager (Single Source)
"""
Manages Orca Universal API Tokens with full permissions (*).
Used by telegram bot, github sync, android bridge — everyone.
"""
import secrets
import time
import json
from loguru import logger
from core.config import config

class APIManager:
    """One manager, one storage file, all callers share the same instance."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self.tokens_file = config.DATA_PATH / "api_tokens.json"
        self.tokens_file.parent.mkdir(parents=True, exist_ok=True)
        self.tokens = self._load()
        if config.ORCA_MASTER:
            self.tokens[config.ORCA_MASTER] = {
                "scope": "*",
                "permissions": ["*"],
                "role": "master",
                "name": "orca-master",
                "created": int(time.time()),
                "active": True,
            }
            self._save()

    def _load(self) -> dict:
        if self.tokens_file.exists():
            try:
                return json.loads(self.tokens_file.read_text())
            except Exception:
                return {}
        return {}

    def _save(self):
        self.tokens_file.write_text(json.dumps(self.tokens, indent=2))

    def create_token(self, name: str = "agent", scope: str = "*", permissions=None) -> str:
        """Generate a new token with full permissions by default."""
        raw = f"orca_live_{secrets.token_urlsafe(32)}"
        self.tokens[raw] = {
            "name": name,
            "scope": scope,
            "permissions": permissions or ["*"],
            "role": "agent",
            "created": int(time.time()),
            "active": True,
        }
        self._save()
        logger.info(f"Token created: {name}")
        return raw

    def validate(self, token: str) -> bool:
        t = self.tokens.get(token)
        return bool(t and t.get("active") and ("*" in t.get("permissions", []) or t.get("permissions") == ["*"]))

    def revoke(self, token: str) -> bool:
        if token in self.tokens:
            self.tokens[token]["active"] = False
            self._save()
            return True
        return False

    def list_tokens(self) -> list:
        return [{"prefix": k[:20] + "...", **v} for k, v in self.tokens.items()]

    def count(self) -> int:
        return len(self.tokens)

# Module-level singleton
api = APIManager()
