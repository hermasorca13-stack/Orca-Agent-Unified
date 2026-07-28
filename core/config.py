# core/config.py - Orca Agent Production Config Loader
import os
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

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

    # Paths
    ROOT = ROOT
    LOG_PATH = ROOT / "logs" / "orca.log"
    DATA_PATH = ROOT / "data"
    BACKUP_PATH = ROOT / "backups"
    SKILLS_PATH = ROOT / "skills"

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

config = Config()
