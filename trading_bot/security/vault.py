"""Local OS-backed secret vault for ORCA Max Mouny.

Only metadata is written to the project. Secret values live in the host's
credential store through the `keyring` package and are never returned in logs.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_SERVICE = "orca-max-mouny"


class VaultError(RuntimeError):
    pass


class LocalApiVault:
    def __init__(self, metadata_path: Path, *, service: str = _SERVICE):
        self.metadata_path = metadata_path
        self.service = service
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)

    def _backend(self):
        try:
            import keyring
        except ImportError as exc:
            raise VaultError("install keyring to use the local OS credential store") from exc
        backend = keyring.get_keyring()
        if backend.__class__.__name__.lower().endswith("failkeyring"):
            raise VaultError("no usable OS credential backend is available")
        return keyring

    def set_exchange(self, exchange: str, api_key: str, api_secret: str, *, password: str = "", uid: str = "", sandbox: bool = True, enable_withdraw: bool = False) -> None:
        if enable_withdraw:
            raise VaultError("withdrawal permission cannot be stored")
        if not exchange or not api_key or not api_secret:
            raise VaultError("exchange, api key and api secret are required")
        keyring = self._backend()
        prefix = exchange.lower()
        keyring.set_password(self.service, f"{prefix}:api_key", api_key)
        keyring.set_password(self.service, f"{prefix}:api_secret", api_secret)
        if password:
            keyring.set_password(self.service, f"{prefix}:password", password)
        if uid:
            keyring.set_password(self.service, f"{prefix}:uid", uid)
        metadata = self._metadata()
        metadata[prefix] = {"sandbox": bool(sandbox), "enable_withdraw": False, "configured": True}
        self.metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    def get_exchange(self, exchange: str) -> dict[str, Any]:
        keyring = self._backend()
        prefix = exchange.lower()
        api_key = keyring.get_password(self.service, f"{prefix}:api_key")
        api_secret = keyring.get_password(self.service, f"{prefix}:api_secret")
        if not api_key or not api_secret:
            raise VaultError(f"no credentials stored for {exchange}")
        metadata = self._metadata().get(prefix, {})
        return {"name": prefix, "api_key": api_key, "api_secret": api_secret, "password": keyring.get_password(self.service, f"{prefix}:password") or "", "uid": keyring.get_password(self.service, f"{prefix}:uid") or "", **metadata, "enable_withdraw": False}

    def list_exchanges(self) -> list[dict[str, Any]]:
        return [{"name": name, **value, "credentials": "stored"} for name, value in self._metadata().items()]

    def delete_exchange(self, exchange: str) -> None:
        keyring = self._backend()
        prefix = exchange.lower()
        for field in ("api_key", "api_secret", "password", "uid"):
            try:
                keyring.delete_password(self.service, f"{prefix}:{field}")
            except Exception:
                pass
        metadata = self._metadata()
        metadata.pop(prefix, None)
        self.metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    def _metadata(self) -> dict[str, Any]:
        if not self.metadata_path.exists():
            return {}
        return json.loads(self.metadata_path.read_text(encoding="utf-8"))
