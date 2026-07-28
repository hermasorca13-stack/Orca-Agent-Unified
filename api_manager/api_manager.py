# api_manager/api_manager.py - Universal API Token Manager
"""
Manages Orca Universal API Tokens with full permissions for any AI agent
to couple with the project and execute commands.
"""
import hashlib
import secrets
import time
import json
from pathlib import Path
from loguru import logger
from core.config import config

class APIManager:
    def __init__(self):
        self.tokens_file = config.DATA_PATH / "api_tokens.json"
        self.tokens_file.parent.mkdir(parents=True, exist_ok=True)
        self.tokens = self._load()
        # Register the master token from .env
        if config.ORCA_MASTER:
            self.tokens[config.ORCA_MASTER] = {
                "scope": "*",
                "permissions": ["*"],
                "role": "master",
                "created": int(time.time()),
                "active": True,
            }
            self._save()

    def _load(self):
        if self.tokens_file.exists():
            return json.loads(self.tokens_file.read_text())
        return {}

    def _save(self):
        self.tokens_file.write_text(json.dumps(self.tokens, indent=2))

    def create_token(self, name: str, scope: str = "*", permissions=None):
        """Generate new token with full permissions by default."""
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
        logger.info(f"Token created: {name} | scope={scope}")
        return raw

    def validate(self, token: str):
        """Check if token is active and has permissions."""
        t = self.tokens.get(token)
        if not t or not t.get("active"):
            return False
        return t.get("permissions") == ["*"] or "*" in t.get("permissions", [])

    def list_tokens(self):
        return [{"prefix": k[:20] + "...", **v} for k, v in self.tokens.items()]

api = APIManager()
