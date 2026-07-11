from __future__ import annotations
import xml.etree.ElementTree as ET
from loguru import logger
import httpx
from app.collectors.base import RawItem


class ArxivCollector:
    def __init__(self, config: dict) -> None:
        self.query: str = config.get("query", "cat:cs.AI")
        self.max_results: int = config.get("max_results", 20)
        self.keywords: str = config.get("keywords", "")

    async def safe_collect(self) -> list[RawItem]:
        try:
            url = f"http://export.arxiv.org/api/query?search_query={self.query}&start=0&max_results={self.max_results}&sortBy=submittedDate&sortOrder=descending"
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    logger.error(f"arXiv: HTTP {resp.status_code}")
                    return []

            ns = {"atom": "http://www.w3.org/2005/Atom"}
            root = ET.fromstring(resp.text)
            entries = root.findall("atom:entry", ns)
            kw_list = [k.strip().lower() for k in self.keywords.split(",") if k.strip()]
            items = []
            for entry in entries:
                title = entry.findtext("atom:title", "", ns).strip().replace("\n", " ")
                summary = entry.findtext("atom:summary", "", ns).strip().replace("\n", " ")
                link_el = entry.find("atom:link[@type='text/html']", ns)
                if link_el is None:
                    link_el = entry.find("atom:link", ns)
                link = link_el.get("href", "") if link_el is not None else ""
                if kw_list and not any(kw in title.lower() or kw in summary.lower() for kw in kw_list):
                    continue
                items.append(RawItem(title=title, text=summary[:2000], url=link))
            logger.info(f"arXiv: fetched {len(items)} items")
            return items
        except Exception as e:
            logger.error(f"arXiv: {e}")
            return []
