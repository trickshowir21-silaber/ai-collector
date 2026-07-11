from __future__ import annotations
from loguru import logger
import httpx
from app.collectors.base import RawItem


class HackerNewsCollector:
    def __init__(self, config: dict) -> None:
        self.max_items: int = config.get("max_items", 30)
        self.keywords: str = config.get("keywords", "AI,LLM,GPT")

    async def safe_collect(self) -> list[RawItem]:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get("https://hacker-news.firebaseio.com/v0/topstories.json")
                if resp.status_code != 200:
                    logger.error(f"HN: HTTP {resp.status_code}")
                    return []
                story_ids = resp.json()[:80]

            kw_list = [k.strip().lower() for k in self.keywords.split(",") if k.strip()]
            items = []
            async with httpx.AsyncClient(timeout=15.0) as client:
                for sid in story_ids:
                    if len(items) >= self.max_items:
                        break
                    try:
                        resp = await client.get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json")
                        if resp.status_code != 200:
                            continue
                        story = resp.json()
                        title = story.get("title", "")
                        if not title:
                            continue
                        if kw_list and not any(kw in title.lower() for kw in kw_list):
                            continue
                        url = story.get("url", f"https://news.ycombinator.com/item?id={sid}")
                        items.append(RawItem(title=title, text=story.get("text", "") or title, url=url))
                    except Exception:
                        continue
            logger.info(f"HackerNews: fetched {len(items)} items")
            return items
        except Exception as e:
            logger.error(f"HackerNews: {e}")
            return []
