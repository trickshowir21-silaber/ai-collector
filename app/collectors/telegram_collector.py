from __future__ import annotations
import datetime as _dt
from loguru import logger
from app.collectors.base import RawItem
from app.config import settings


class TelegramCollector:
    def __init__(self, config: dict) -> None:
        self.channel: str = config.get("channel", "")

    async def safe_collect(self) -> list[RawItem]:
        if not settings.telethon_api_id or not self.channel:
            return []
        try:
            from telethon import TelegramClient
            client = TelegramCollector._get_client()
            if not client:
                return []
            items: list[RawItem] = []
            async with client:
                async for msg in client.iter_messages(self.channel, limit=20):
                    if msg.text:
                        pub = msg.date.replace(tzinfo=_dt.timezone.utc) if msg.date else None
                        url = f"https://t.me/{self.channel}/{msg.id}"
                        items.append(RawItem(title=msg.text[:100], text=msg.text, url=url, published_at=pub))
            logger.info(f"Telegram @{self.channel}: fetched {len(items)} items")
            return items
        except Exception as e:
            logger.error(f"Telegram @{self.channel}: {e}")
            return []

    @staticmethod
    def _get_client():
        if not settings.telethon_api_id or not settings.telethon_api_hash:
            return None
        from telethon import TelegramClient
        return TelegramClient(settings.telethon_session_name or "curator_session", settings.telethon_api_id, settings.telethon_api_hash)
