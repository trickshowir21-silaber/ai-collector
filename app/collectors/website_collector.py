from __future__ import annotations
from loguru import logger
import httpx
from app.collectors.base import RawItem


class WebsiteCollector:
    def __init__(self, config: dict) -> None:
        self.url: str = config.get("url", "")

    async def safe_collect(self) -> list[RawItem]:
        if not self.url:
            return []
        try:
            from bs4 import BeautifulSoup
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(self.url, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code != 200:
                    return []
                soup = BeautifulSoup(resp.text, "lxml")
                title = soup.title.string if soup.title else ""
                text = soup.get_text(separator="\n", strip=True)[:5000]
                return [RawItem(title=title, text=text, url=self.url)]
        except Exception as e:
            logger.error(f"Website {self.url}: {e}")
            return []
