from __future__ import annotations
import asyncio
from aiogram import Router, F
from aiogram.types import Message
from loguru import logger
from sqlalchemy import select
from app.config import settings
from app.database import async_session_factory
from app.models.models import User

router = Router(name="commands")


async def is_auth(uid: int) -> bool:
    if uid == settings.super_admin_id:
        return True
    async with async_session_factory() as s:
        r = await s.execute(select(User).where(User.telegram_id == uid))
        return r.scalar_one_or_none() is not None


@router.message(F.text == "/panel")
async def cmd_panel(message: Message) -> None:
    if not message.from_user or not await is_auth(message.from_user.id):
        return
    from app.handlers.panel import main_kb
    await message.answer("پنل مدیریت", reply_markup=main_kb())


@router.message(F.text == "/crawl")
async def cmd_crawl(message: Message) -> None:
    if not message.from_user or not await is_auth(message.from_user.id):
        return
    from app.services.scheduler import _run_collectors
    asyncio.create_task(_run_collectors())
    await message.answer("جمع‌آوری شروع شد!")


@router.message(F.text == "/digest")
async def cmd_digest(message: Message) -> None:
    if not message.from_user or not await is_auth(message.from_user.id):
        return
    from app.services.scheduler import _run_digest
    asyncio.create_task(_run_digest())
    await message.answer("خلاصه‌سازی شروع شد!")
