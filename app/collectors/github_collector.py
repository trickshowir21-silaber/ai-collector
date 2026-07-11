from __future__ import annotations
import datetime as _dt
from loguru import logger
import httpx
from app.collectors.base import RawItem


class GitHubCollector:
    def __init__(self, config: dict) -> None:
        self.language: str = config.get("language", "")

    async def safe_collect(self) -> list[RawItem]:
        if not self.language:
            return []
        try:
            since = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()
            url = f"https://api.github.com/search/repositories?q=language:{self.language}+created:>{since}&sort=stars&order=desc&per_page=10"
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, headers={"Accept": "application/vnd.github.v3+json"})
                if resp.status_code != 200:
                    logger.error(f"GitHub: HTTP {resp.status_code}")
                    return []
                data = resp.json()
            items = []
            for repo in data.get("items", []):
                name = repo.get("full_name", "")
                desc = repo.get("description", "") or ""
                link = repo.get("html_url", "")
                stars = repo.get("stargazers_count", 0)
                items.append(RawItem(title=f"{name} ({stars}* )", text=desc, url=link))
            logger.info(f"GitHub [{self.language}]: fetched {len(items)} items")
            return items
        except Exception as e:
            logger.error(f"GitHub: {e}")
            return []
