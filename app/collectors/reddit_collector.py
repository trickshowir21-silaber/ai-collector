from __future__ import annotations
from loguru import logger
import httpx
from app.collectors.base import RawItem


class RedditCollector:
    def __init__(self, config: dict) -> None:
        self.subreddit: str = config.get("subreddit", "")

    async def safe_collect(self) -> list[RawItem]:
        if not self.subreddit:
            return []
        try:
            url = f"https://www.reddit.com/r/{self.subreddit}/hot.json?limit=20"
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "AICuratorBot/1.0"})
                if resp.status_code != 200:
                    logger.error(f"Reddit r/{self.subreddit}: HTTP {resp.status_code}")
                    return []
                data = resp.json()
            items = []
            for child in data.get("data", {}).get("children", []):
                post = child.get("data", {})
                title = post.get("title", "")
                selftext = post.get("selftext", "")
                link = f"https://reddit.com{post.get('permalink', '')}"
                items.append(RawItem(title=title, text=selftext[:2000], url=link))
            logger.info(f"Reddit r/{self.subreddit}: fetched {len(items)} items")
            return items
        except Exception as e:
            logger.error(f"Reddit r/{self.subreddit}: {e}")
            return []
