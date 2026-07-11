from __future__ import annotations
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _get(key: str, default: str = "") -> str:
    """Read from environment variable."""
    return os.environ.get(key, default)


class Settings:
    def __init__(self) -> None:
        self.bot_token: str = _get("BOT_TOKEN")
        self.super_admin_id: int = int(_get("SUPER_ADMIN_ID", "0"))
        self.database_url: str = _get("DATABASE_URL", f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'curator.db'}")
        self.openai_api_key: str = _get("OPENAI_API_KEY")
        self.openai_model: str = _get("OPENAI_MODEL", "gpt-4o-mini")
        self.mimo_api_key: str = _get("MIMO_API_KEY")
        self.mimo_model: str = _get("MIMO_MODEL", "MiMo-7B-RL")
        self.mimo_base_url: str = _get("MIMO_BASE_URL", "https://api.mimo.xiaomi.com/v1/chat/completions")
        self.deepseek_api_key: str = _get("DEEPSEEK_API_KEY")
        self.deepseek_model: str = _get("DEEPSEEK_MODEL", "deepseek-chat")
        self.gemini_api_key: str = _get("GEMINI_API_KEY")
        self.telethon_api_id: int = int(_get("TELETHON_API_ID", "0"))
        self.telethon_api_hash: str = _get("TELETHON_API_HASH")
        self.telethon_session_name: str = _get("TELETHON_SESSION_NAME", "curator_session")
        self.twitter_bearer_token: str = _get("TWITTER_BEARER_TOKEN")
        self.digest_hour: int = int(_get("DIGEST_HOUR", "9"))
        self.digest_minute: int = int(_get("DIGEST_MINUTE", "0"))
        self.digest_max_items: int = int(_get("DIGEST_MAX_ITEMS", "10"))
        self.log_level: str = _get("LOG_LEVEL", "INFO")


settings = Settings()
