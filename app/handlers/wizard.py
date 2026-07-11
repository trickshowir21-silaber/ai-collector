from __future__ import annotations
import json

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from app.config import settings
from app.database import async_session_factory
from app.models.models import User, Source, Keyword, Hashtag, Setting

router = Router(name="wizard")


async def is_auth(uid: int) -> bool:
    if uid == settings.super_admin_id:
        return True
    async with async_session_factory() as s:
        r = await s.execute(select(User).where(User.telegram_id == uid))
        return r.scalar_one_or_none() is not None


class AddSource(StatesGroup):
    type = State()
    name = State()
    config = State()


class AddKeyword(StatesGroup):
    word = State()


class AddHashtag(StatesGroup):
    tag = State()


class AddReceiver(StatesGroup):
    chat_id = State()


class AddAdmin(StatesGroup):
    chat_id = State()


class SetTime(StatesGroup):
    hour = State()


class SetCount(StatesGroup):
    count = State()


class SetScore(StatesGroup):
    score = State()


@router.callback_query(F.data == "wiz:src")
async def wiz_src_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await is_auth(callback.from_user.id):
        return
    btns = [
        [InlineKeyboardButton(text="RSS", callback_data="wsrc:rss")],
        [InlineKeyboardButton(text="Telegram", callback_data="wsrc:telegram")],
        [InlineKeyboardButton(text="Twitter", callback_data="wsrc:twitter")],
        [InlineKeyboardButton(text="Website", callback_data="wsrc:website")],
        [InlineKeyboardButton(text="بازگشت", callback_data="p:sources")],
    ]
    await callback.message.edit_text("نوع منبع:", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))
    await state.set_state(AddSource.type)


@router.callback_query(F.data.startswith("wsrc:"))
async def wiz_src_type(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await is_auth(callback.from_user.id):
        return
    stype = callback.data.split(":")[1]
    await state.update_data(type=stype)
    await callback.message.edit_text("اسم منبع:\n\nمثال: OpenAI Blog")
    await state.set_state(AddSource.name)


@router.message(AddSource.name)
async def wiz_src_name(message: Message, state: FSMContext) -> None:
    if not message.from_user or not await is_auth(message.from_user.id):
        return
    await state.update_data(name=(message.text or "").strip())
    data = await state.get_data()
    stype = data.get("type", "rss")
    prompts = {
        "rss": "آدرس RSS:\n\nمثال: https://openai.com/blog/rss",
        "telegram": "یوزرنیم کانال:\n\nمثال: OpenAI",
        "twitter": "یوزرنیم توییتر:\n\nمثال: OpenAI",
        "website": "آدرس وبسایت:",
    }
    await message.answer(prompts.get(stype, "آدرس:"))
    await state.set_state(AddSource.config)


@router.message(AddSource.config)
async def wiz_src_config(message: Message, state: FSMContext) -> None:
    if not message.from_user or not await is_auth(message.from_user.id):
        return
    data = await state.get_data()
    stype = data.get("type", "rss")
    name = data.get("name", "New Source")
    val = (message.text or "").strip()
    config_map = {
        "rss": lambda v: {"url": v},
        "telegram": lambda v: {"channel": v.lstrip("@")},
        "twitter": lambda v: {"username": v.lstrip("@")},
        "website": lambda v: {"url": v},
    }
    config = config_map.get(stype, lambda v: {"url": v})(val)
    async with async_session_factory() as s:
        s.add(Source(name=name, type=stype, config_json=json.dumps(config), is_active=True))
        await s.commit()
    await message.answer(f"منبع «{name}» اضافه شد!")
    await state.clear()


@router.callback_query(F.data == "wiz:kw_pos")
async def wiz_kw_pos(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await is_auth(callback.from_user.id):
        return
    await state.update_data(is_neg=False)
    await callback.message.edit_text("کلمه مثبت جدید:\n\nمثال: AI")
    await state.set_state(AddKeyword.word)


@router.callback_query(F.data == "wiz:kw_neg")
async def wiz_kw_neg(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await is_auth(callback.from_user.id):
        return
    await state.update_data(is_neg=True)
    await callback.message.edit_text("کلمه منفی جدید:\n\nمثال: spam")
    await state.set_state(AddKeyword.word)


@router.message(AddKeyword.word)
async def wiz_kw_word(message: Message, state: FSMContext) -> None:
    if not message.from_user or not await is_auth(message.from_user.id):
        return
    data = await state.get_data()
    word = (message.text or "").strip()
    if not word:
        await message.answer("کلمه خالیه.")
        return
    async with async_session_factory() as s:
        s.add(Keyword(word=word, is_negative=data.get("is_neg", False)))
        await s.commit()
    label = "منفی" if data.get("is_neg") else "مثبت"
    await message.answer(f"کلمه {label} «{word}» اضافه شد!")
    await state.clear()


@router.callback_query(F.data == "wiz:ht_add")
async def wiz_ht_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await is_auth(callback.from_user.id):
        return
    await callback.message.edit_text("هشتگ جدید:\n\nمثال: ChatGPT")
    await state.set_state(AddHashtag.tag)


@router.message(AddHashtag.tag)
async def wiz_ht_tag(message: Message, state: FSMContext) -> None:
    if not message.from_user or not await is_auth(message.from_user.id):
        return
    tag = (message.text or "").strip().lstrip("#")
    if not tag:
        await message.answer("هشتگ خالیه.")
        return
    async with async_session_factory() as s:
        s.add(Hashtag(tag=tag))
        await s.commit()
    await message.answer(f"هشتگ #{tag} اضافه شد!")
    await state.clear()


@router.callback_query(F.data == "wiz:rc_add")
async def wiz_rc_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await is_auth(callback.from_user.id):
        return
    await callback.message.edit_text("Chat ID دریافت‌کننده:\n\nمثال: -1001234567890")
    await state.set_state(AddReceiver.chat_id)


@router.message(AddReceiver.chat_id)
async def wiz_rc_id(message: Message, state: FSMContext) -> None:
    if not message.from_user or not await is_auth(message.from_user.id):
        return
    try:
        cid = int((message.text or "").strip())
    except:
        await message.answer("عدد بفرست.")
        return
    async with async_session_factory() as s:
        rv = (await s.execute(select(Setting.value).where(Setting.key == "receiver_ids"))).scalar_one_or_none()
        try:
            rids = json.loads(rv) if rv else []
        except:
            rids = []
        if cid not in rids:
            rids.append(cid)
        r = await s.execute(select(Setting).where(Setting.key == "receiver_ids"))
        st = r.scalar_one_or_none()
        if st:
            st.value = json.dumps(rids)
        else:
            s.add(Setting(key="receiver_ids", value=json.dumps(rids)))
        await s.commit()
    await message.answer(f"دریافت‌کننده {cid} اضافه شد!\nکل: {len(rids)} نفر")
    await state.clear()


@router.callback_query(F.data == "wiz:adm_add")
async def wiz_adm_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or callback.from_user.id != settings.super_admin_id:
        return
    await callback.message.edit_text("Chat ID مدیر جدید:")
    await state.set_state(AddAdmin.chat_id)


@router.message(AddAdmin.chat_id)
async def wiz_adm_id(message: Message, state: FSMContext) -> None:
    if not message.from_user or message.from_user.id != settings.super_admin_id:
        return
    try:
        cid = int((message.text or "").strip())
    except:
        await message.answer("عدد بفرست.")
        return
    async with async_session_factory() as s:
        existing = (await s.execute(select(User).where(User.telegram_id == cid))).scalar_one_or_none()
        if existing:
            await message.answer("این ID قبلاً ثبت شده.")
        else:
            s.add(User(telegram_id=cid, is_super_admin=False))
            await s.commit()
            await message.answer(f"مدیر {cid} اضافه شد!")
    await state.clear()


@router.callback_query(F.data == "wiz:time")
async def wiz_time_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await is_auth(callback.from_user.id):
        return
    await callback.message.edit_text("ساعت ارسال خلاصه (0-23):")
    await state.set_state(SetTime.hour)


@router.message(SetTime.hour)
async def wiz_time_hour(message: Message, state: FSMContext) -> None:
    if not message.from_user or not await is_auth(message.from_user.id):
        return
    try:
        h = int((message.text or "").strip())
        assert 0 <= h <= 23
    except:
        await message.answer("عدد 0 تا 23 بفرست.")
        return
    async with async_session_factory() as s:
        r = await s.execute(select(Setting).where(Setting.key == "digest_hour"))
        st = r.scalar_one_or_none()
        if st:
            st.value = str(h)
        else:
            s.add(Setting(key="digest_hour", value=str(h)))
        await s.commit()
    await message.answer(f"ساعت {h}:00 تنظیم شد.")
    await state.clear()


@router.callback_query(F.data == "wiz:count")
async def wiz_count_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await is_auth(callback.from_user.id):
        return
    await callback.message.edit_text("حداکثر تعداد مطلب:")
    await state.set_state(SetCount.count)


@router.message(SetCount.count)
async def wiz_count_val(message: Message, state: FSMContext) -> None:
    if not message.from_user or not await is_auth(message.from_user.id):
        return
    try:
        n = int((message.text or "").strip())
        assert n > 0
    except:
        await message.answer("عدد مثبت بفرست.")
        return
    async with async_session_factory() as s:
        r = await s.execute(select(Setting).where(Setting.key == "digest_max_items"))
        st = r.scalar_one_or_none()
        if st:
            st.value = str(n)
        else:
            s.add(Setting(key="digest_max_items", value=str(n)))
        await s.commit()
    await message.answer(f"حداکثر {n} مطلب تنظیم شد.")
    await state.clear()


@router.callback_query(F.data == "wiz:score")
async def wiz_score_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await is_auth(callback.from_user.id):
        return
    await callback.message.edit_text("حداقل امتیاز (0-10):")
    await state.set_state(SetScore.score)


@router.message(SetScore.score)
async def wiz_score_val(message: Message, state: FSMContext) -> None:
    if not message.from_user or not await is_auth(message.from_user.id):
        return
    try:
        n = float((message.text or "").strip())
        assert 0 <= n <= 10
    except:
        await message.answer("عدد 0 تا 10 بفرست.")
        return
    async with async_session_factory() as s:
        r = await s.execute(select(Setting).where(Setting.key == "min_score"))
        st = r.scalar_one_or_none()
        if st:
            st.value = str(n)
        else:
            s.add(Setting(key="min_score", value=str(n)))
        await s.commit()
    await message.answer(f"حداقل امتیاز {n} تنظیم شد.")
    await state.clear()
