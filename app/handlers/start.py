from __future__ import annotations
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from loguru import logger
from sqlalchemy import select
from app.config import settings
from app.database import async_session_factory
from app.models.models import User

router = Router(name="start")


@router.message(F.text == "/start")
async def cmd_start(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    if uid != settings.super_admin_id:
        logger.warning(f"Unauthorized /start: {uid}")
        await message.answer("دسترسی ندارید.")
        return

    async with async_session_factory() as s:
        existing = (await s.execute(select(User).where(User.telegram_id == uid))).scalar_one_or_none()
        if not existing:
            s.add(User(
                telegram_id=uid,
                username=message.from_user.username if message.from_user else None,
                is_super_admin=True,
            ))
            await s.commit()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="پنل مدیریت", callback_data="p:main")],
    ])
    await message.answer(
        f"ربات کیوریتور AI\n\n"
        f"سلام {message.from_user.first_name if message.from_user else ''}!\n\n"
        f"منابع خبری رو تنظیم کن\n"
        f"ربات خودکار جمع‌آوری میکنه\n"
        f"خلاصه‌ها رو بفرست به کانال/گروه",
        reply_markup=kb,
    )
