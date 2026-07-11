from __future__ import annotations
import json
from datetime import datetime, timezone

from aiogram import Bot
from loguru import logger
from sqlalchemy import select

from app.database import async_session_factory
from app.models.models import ContentItem, DeliveredLog, Setting
from app.config import settings
from app.utils.helpers import format_content_html, format_digest_html


async def deliver_urgent(bot: Bot, item: ContentItem) -> None:
    async with async_session_factory() as s:
        rv = (await s.execute(select(Setting.value).where(Setting.key == "receiver_ids"))).scalar_one_or_none()
        try:
            rids = json.loads(rv) if rv else []
        except:
            rids = []
    if not rids:
        return
    tags = []
    if item.tags_json:
        try:
            tags = json.loads(item.tags_json)
        except:
            pass
    msg = format_content_html(
        item.title, item.summary_en or item.summary_fa or "",
        item.url, item.category, item.score, tags,
    )
    for cid in rids:
        try:
            await bot.send_message(chat_id=cid, text=f"URGENT!\n\n{msg}", parse_mode="HTML", disable_web_page_preview=False)
            async with async_session_factory() as s:
                s.add(DeliveredLog(content_id=item.id, chat_id=cid))
                await s.commit()
        except Exception as e:
            logger.error(f"Urgent delivery {cid}: {e}")


async def deliver_digest(bot: Bot) -> None:
    async with async_session_factory() as s:
        rv = (await s.execute(select(Setting.value).where(Setting.key == "receiver_ids"))).scalar_one_or_none()
        try:
            rids = json.loads(rv) if rv else []
        except:
            rids = []
        items_r = (await s.execute(
            select(ContentItem)
            .where(ContentItem.processed == True, ContentItem.delivered == False)
            .order_by(ContentItem.score.desc())
            .limit(settings.digest_max_items)
        )).scalars().all()

    if not rids or not items_r:
        logger.info("Digest: nothing to send")
        return

    items_dicts = []
    for it in items_r:
        tags = []
        if it.tags_json:
            try:
                tags = json.loads(it.tags_json)
            except:
                pass
        items_dicts.append({
            "title": it.title, "summary": it.summary_en or it.summary_fa or "",
            "url": it.url, "category": it.category, "score": it.score, "hashtags": tags,
        })

    digest_html = format_digest_html(items_dicts)
    logger.info(f"Digest: sending {len(items_dicts)} items to {len(rids)} receivers")
    sent = 0
    for cid in rids:
        try:
            await bot.send_message(chat_id=cid, text=digest_html, parse_mode="HTML", disable_web_page_preview=False)
            sent += 1
        except Exception as e:
            logger.error(f"Digest -> {cid}: {e}")

    async with async_session_factory() as s:
        for it in items_r:
            it.delivered = True
        await s.commit()
    logger.info(f"Digest complete: {len(items_dicts)} items -> {sent}/{len(rids)} receivers")
