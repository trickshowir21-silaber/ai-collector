from __future__ import annotations
import re
from typing import Optional
from bs4 import BeautifulSoup


def clean_content(title: str, text: str, html: Optional[str] = None) -> tuple[str, str]:
    clean_title = _strip_html(title).strip()
    if html:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
    clean_text = _strip_html(text)
    clean_text = re.sub(r"\n{3,}", "\n\n", clean_text).strip()
    clean_text = re.sub(r"[ \t]{2,}", " ", clean_text)
    return clean_title[:500], clean_text[:10000]


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)
