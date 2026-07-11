from __future__ import annotations
import datetime as _dt
from loguru import logger
import feedparser
import httpx
from app.collectors.base import RawItem


class RSSCollector:
    def __init__(self, config: dict) -> None:
        self.url: str = config.get("url", "")

    async def safe_collect(self) -> list[RawItem]:
        if not self.url:
            return []
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(self.url, headers={"User-Agent": "Mozilla/5.0 AICuratorBot/1.0"})
                if resp.status_code != 200:
                    logger.error(f"RSS [{self.url[:40]}]: HTTP {resp.status_code}")
                    return []
                feed = feedparser.parse(resp.text)
        except Exception as e:
            logger.error(f"RSS [{self.url[:40]}]: {e}")
            return []

        items: list[RawItem] = []
        for entry in feed.entries[:30]:
            title = getattr(entry, "title", "") or ""
            link = getattr(entry, "link", None)
            summary = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published = _dt.datetime(*entry.published_parsed[:6], tzinfo=_dt.timezone.utc)
                except Exception:
                    pass
            items.append(RawItem(title=title, text=summary, url=link, html=summary, published_at=published))

        logger.info(f"RSS [{self.url[:60]}]: fetched {len(items)} items")
        return items
