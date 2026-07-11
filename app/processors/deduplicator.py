from __future__ import annotations
import hashlib
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import ContentItem


async def compute_hash(url: str | None, text: str) -> str:
    key = url if url else text[:500]
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


async def is_duplicate(session: AsyncSession, url: str | None, text: str) -> bool:
    h = await compute_hash(url, text)
    result = await session.execute(select(ContentItem.id).where(ContentItem.content_hash == h).limit(1))
    return result.scalar_one_or_none() is not None
