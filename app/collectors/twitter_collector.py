from __future__ import annotations
from loguru import logger
import httpx
from app.collectors.base import RawItem
from app.config import settings


class TwitterCollector:
    def __init__(self, config: dict) -> None:
        self.username: str = config.get("username", "")

    async def safe_collect(self) -> list[RawItem]:
        if not settings.twitter_bearer_token or not self.username:
            return []
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"https://api.twitter.com/2/tweets/search/recent?query=from:{self.username}&max_results=10",
                    headers={"Authorization": f"Bearer {settings.twitter_bearer_token}"},
                )
                if resp.status_code != 200:
                    logger.error(f"Twitter @{self.username}: HTTP {resp.status_code}")
                    return []
                data = resp.json().get("data", [])
                items = []
                for tweet in data:
                    url = f"https://twitter.com/{self.username}/status/{tweet['id']}"
                    items.append(RawItem(title=tweet["text"][:100], text=tweet["text"], url=url))
                logger.info(f"Twitter @{self.username}: fetched {len(items)} items")
                return items
        except Exception as e:
            logger.error(f"Twitter @{self.username}: {e}")
            return []
