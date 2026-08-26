"""Validated configuration for ORCA Max Mouny.

Secrets are read from environment variables only. Never commit a populated .env file.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from trading_bot.models import TradingMode


class ConfigurationError(ValueError):
    """Raised when configuration cannot safely start the engine."""


@dataclass(frozen=True)
class ExchangeCredentials:
    name: str
    api_key: str = ""
    api_secret: str = ""
    password: str = ""
    uid: str = ""
    sandbox: bool = True
    enable_withdraw: bool = False

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.api_secret)


@dataclass(frozen=True)
class Settings:
    name: str = "ORCA Max Mouny"
    mode: TradingMode = TradingMode.PAPER
    state_dir: Path = Path("data/orca_max_mouny")
    audit_log: Path = Path("data/orca_max_mouny/audit.jsonl")
    database: Path = Path("data/orca_max_mouny/orca.sqlite3")
    allowed_exchanges: tuple[str, ...] = ("binance", "coinbase", "kraken")
    active_exchanges: tuple[str, ...] = ()
    max_order_risk_pct: float = 0.01
    min_order_risk_pct: float = 0.005
    directional_leverage_max: float = 2.0
    arbitrage_leverage_min: float = 3.0
    arbitrage_leverage_max: float = 6.0
    external_reserve_pct: float = 0.20
    max_data_age_seconds: float = 3.0
    max_latency_ms: float = 500.0
    max_daily_loss_pct: float = 0.02
    max_monthly_loss_pct: float = 0.02
    max_drawdown_pct: float = 0.20
    max_atr_pct: float = 0.05
    min_volume_24h_usd: float = 500_000_000.0
    min_reward_risk: float = 2.0
    fear_greed_min: float = 20.0
    fear_greed_max: float = 80.0
    stablecoin_symbols: tuple[str, ...] = ("USDT", "USDC", "DAI")
    credentials: tuple[ExchangeCredentials, ...] = field(default_factory=tuple)

    def ensure_dirs(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.audit_log.parent.mkdir(parents=True, exist_ok=True)
        self.database.parent.mkdir(parents=True, exist_ok=True)

    def validate_startup(self) -> None:
        if not 0.0 < self.min_order_risk_pct <= self.max_order_risk_pct <= 0.01:
            raise ConfigurationError("risk per trade must be within 0.5%-1.0%")
        if self.directional_leverage_max > 2.0:
            raise ConfigurationError("directional leverage cannot exceed 2x")
        if not 0.0 < self.external_reserve_pct <= 1.0:
            raise ConfigurationError("external reserve must be a positive fraction")
        for credential in self.credentials:
            if credential.enable_withdraw:
                raise ConfigurationError(f"withdrawal permission is forbidden: {credential.name}")
        if self.mode == TradingMode.LIVE:
            if os.getenv("ORCA_LIVE_CONFIRM", "") != "I_UNDERSTAND_ORCA_LIVE":
                raise ConfigurationError("live mode requires ORCA_LIVE_CONFIRM=I_UNDERSTAND_ORCA_LIVE")
            configured = {item.name for item in self.credentials if item.configured}
            missing = set(self.active_exchanges) - configured
            if missing:
                raise ConfigurationError(f"live mode requires credentials for: {sorted(missing)}")


def _csv(name: str, default: Iterable[str] = ()) -> tuple[str, ...]:
    raw = os.getenv(name, "")
    if not raw.strip():
        return tuple(default)
    return tuple(item.strip().lower() for item in raw.split(",") if item.strip())


def _float(name: str, default: float) -> float:
    value = os.getenv(name)
    return default if value in (None, "") else float(value)


def _credential_from_env_or_vault(name: str) -> ExchangeCredentials:
    prefix = name.upper()
    values = {
        "api_key": os.getenv(f"ORCA_{prefix}_API_KEY", ""),
        "api_secret": os.getenv(f"ORCA_{prefix}_API_SECRET", ""),
        "password": os.getenv(f"ORCA_{prefix}_PASSWORD", ""),
        "uid": os.getenv(f"ORCA_{prefix}_UID", ""),
        "sandbox": os.getenv(f"ORCA_{prefix}_SANDBOX", "1") == "1",
        "enable_withdraw": os.getenv(f"ORCA_{prefix}_ENABLE_WITHDRAW", "0") == "1",
    }
    if not values["api_key"] or not values["api_secret"]:
        try:
            from trading_bot.security.vault import LocalApiVault
            stored = LocalApiVault(Path(os.getenv("ORCA_CREDENTIAL_METADATA", "data/orca_max_mouny/credentials.json"))).get_exchange(name)
            values.update({key: stored[key] for key in ("api_key", "api_secret", "password", "uid", "sandbox", "enable_withdraw") if key in stored})
        except Exception:
            pass
    return ExchangeCredentials(name=name, **values)


def load_settings() -> Settings:
    mode = TradingMode(os.getenv("ORCA_TRADING_MODE", "paper").lower())
    active = _csv("ORCA_ACTIVE_EXCHANGES")
    credentials = tuple(_credential_from_env_or_vault(name) for name in _csv("ORCA_CREDENTIAL_EXCHANGES", ("binance", "coinbase", "kraken")))
    settings = Settings(
        mode=mode,
        state_dir=Path(os.getenv("ORCA_STATE_DIR", "data/orca_max_mouny")),
        audit_log=Path(os.getenv("ORCA_AUDIT_LOG", "data/orca_max_mouny/audit.jsonl")),
        database=Path(os.getenv("ORCA_DATABASE", "data/orca_max_mouny/orca.sqlite3")),
        active_exchanges=active,
        max_order_risk_pct=_float("ORCA_MAX_ORDER_RISK_PCT", 0.01),
        min_order_risk_pct=_float("ORCA_MIN_ORDER_RISK_PCT", 0.005),
        max_daily_loss_pct=_float("ORCA_MAX_DAILY_LOSS_PCT", 0.02),
        max_monthly_loss_pct=_float("ORCA_MAX_MONTHLY_LOSS_PCT", 0.02),
        credentials=credentials,
    )
    settings.ensure_dirs()
    settings.validate_startup()
    return settings
