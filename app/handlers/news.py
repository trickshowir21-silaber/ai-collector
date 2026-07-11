from __future__ import annotations
import json
import asyncio
from datetime import datetime, timezone, timedelta

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from loguru import logger
from sqlalchemy import select, func as sqlfunc

from app.config import settings
from app.database import async_session_factory
from app.models.models import User, Source, ContentItem, Bookmark, Setting
from app.utils.helpers import format_single_item_html, is_persian, h

router = Router(name="news")


async def is_auth(uid):
    if uid == settings.super_admin_id:
        return True
    async with async_session_factory() as s:
        r = await s.execute(select(User).where(User.telegram_id == uid))
        return r.scalar_one_or_none() is not None


async def safe_answer(cb, text="", alert=False):
    try:
        await cb.answer(text, show_alert=alert)
    except:
        pass


class NewsFilter(StatesGroup):
    menu = State()
    batch_input = State()
    custom_date = State()


CATS = {
    "tutorial": "آموزشی", "news": "خبر", "tool": "ابزار",
    "prompt": "پرامپت", "paper": "مقاله", "other": "متفرقه",
}
SRC_EMOJI = {
    "rss": "RSS", "telegram": "TG", "twitter": "TW", "reddit": "RD",
    "website": "WEB", "github": "GH", "hackernews": "HN", "arxiv": "AX",
}


@router.callback_query(F.data == "p:news")
async def cb_news(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await is_auth(callback.from_user.id):
        return
    async with async_session_factory() as s:
        rv = (await s.execute(select(Setting.value).where(Setting.key == "receiver_ids"))).scalar_one_or_none()
        try:
            rids = json.loads(rv) if rv else []
        except:
            rids = []
        total = (await s.execute(select(sqlfunc.count(ContentItem.id)).where(ContentItem.processed == True))).scalar() or 0
        undel = (await s.execute(select(sqlfunc.count(ContentItem.id)).where(
            ContentItem.processed == True, ContentItem.delivered == False))).scalar() or 0
        now = datetime.now(timezone.utc)
        today_s = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_n = (await s.execute(select(sqlfunc.count(ContentItem.id)).where(
            ContentItem.processed == True, ContentItem.created_at >= today_s))).scalar() or 0

    txt = (
        f"دریافت اخبار\n\n"
        f"کل مطالب: {total}\n"
        f"امروز: {today_n}\n"
        f"آماده ارسال: {undel}\n"
        f"دریافت‌کنندگان: {len(rids)}"
    )
    if not rids:
        txt += "\n\nدریافت‌کننده تنظیم نشده!"
    if not total:
        txt += "\n\nمطلبی نیست. اول جمع‌آوری رو بزن."

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="جمع‌آوری الان", callback_data="fn:fetch")],
        [InlineKeyboardButton(text="فیلتر و مشاهده مطالب", callback_data="fn:menu")],
        [InlineKeyboardButton(text="ارسال خلاصه سریع", callback_data="fn:quick_send")],
        [InlineKeyboardButton(text="لیست مهم", callback_data="fnbk:0")],
        [InlineKeyboardButton(text="بازگشت", callback_data="p:main")],
    ])
    await safe_answer(callback)
    try:
        await callback.message.edit_text(txt, reply_markup=kb)
    except:
        await callback.message.answer(txt, reply_markup=kb)


@router.callback_query(F.data == "fn:fetch")
async def cb_fetch(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_auth(callback.from_user.id):
        return
    await safe_answer(callback, "Working...")
    async with async_session_factory() as s:
        active = (await s.execute(select(sqlfunc.count(Source.id)).where(Source.is_active == True))).scalar() or 0
    if not active:
        await callback.message.answer("No active sources! Add from Sources menu.")
        return
    from app.services.scheduler import _run_collectors
    asyncio.create_task(_run_collectors())
    await callback.message.answer(f"Crawl started! {active} active sources | 2-10 min")


@router.callback_query(F.data == "fn:quick_send")
async def cb_quick_send(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_auth(callback.from_user.id):
        return
    await safe_answer(callback, "Working...")
    async with async_session_factory() as s:
        rv = (await s.execute(select(Setting.value).where(Setting.key == "receiver_ids"))).scalar_one_or_none()
        try:
            rids = json.loads(rv) if rv else []
        except:
            rids = []
    if not rids:
        await callback.message.answer("No receivers! Add from Receivers menu.")
        return
    from app.services.delivery import deliver_digest
    await deliver_digest(callback.bot)
    await callback.message.answer("Digest sent!")


# ── FILTER MENU ──

TIME_LABELS = {"t": "امروز", "w": "این هفته", "m": "این ماه", "a": "همه زمان‌ها", "c": "بازه سفارشی"}
BATCH_LABELS = {"l": "آخرین دفعه", "a": "همه دفعات"}


async def _get_filter_text(data: dict) -> str:
    tl = TIME_LABELS.get(data.get("time", "a"), "همه")
    bl = BATCH_LABELS.get(str(data.get("batch", "a")), f"دفعه #{data['batch']}")
    sl = "همه" if not data.get("sources") else f"{len(data['sources'])} منبع"
    cl = "همه" if not data.get("categories") else f"{len(data['categories'])} موضوع"
    return (
        f"فیلتر مطالب\n\n"
        f"زمان: {tl}\n"
        f"جمع‌آوری: {bl}\n"
        f"منبع: {sl}\n"
        f"موضوع: {cl}"
    )


def _filter_menu_kb(data: dict) -> InlineKeyboardMarkup:
    t = data.get("time", "a")
    b = str(data.get("batch", "a"))
    has_src = bool(data.get("sources"))
    has_cat = bool(data.get("categories"))

    def mark(key, val):
        return " *" if key == val else ""

    btns = [
        [
            InlineKeyboardButton(text=f"امروز{mark(t,'t')}", callback_data="fn:t:t"),
            InlineKeyboardButton(text=f"هفته{mark(t,'w')}", callback_data="fn:t:w"),
            InlineKeyboardButton(text=f"ماه{mark(t,'m')}", callback_data="fn:t:m"),
            InlineKeyboardButton(text=f"همه{mark(t,'a')}", callback_data="fn:t:a"),
        ],
        [InlineKeyboardButton(text=f"بازه سفارشی{mark(t,'c')}", callback_data="fn:t:c")],
        [
            InlineKeyboardButton(text=f"آخرین دفعه{mark(b,'l')}", callback_data="fn:b:l"),
            InlineKeyboardButton(text=f"همه دفعات{mark(b,'a')}", callback_data="fn:b:a"),
            InlineKeyboardButton(text="دفعه خاص", callback_data="fn:b:ask"),
        ],
        [
            InlineKeyboardButton(text=f"{'* ' if not has_src else ''}همه منابع", callback_data="fn:s:all"),
            InlineKeyboardButton(text=f"{'* ' if has_src else ''}انتخاب منبع ({len(data.get('sources', []))})", callback_data="fn:s:sel"),
        ],
        [
            InlineKeyboardButton(text=f"{'* ' if not has_cat else ''}همه موضوعات", callback_data="fn:c:all"),
            InlineKeyboardButton(text=f"{'* ' if has_cat else ''}انتخاب موضوع ({len(data.get('categories', []))})", callback_data="fn:c:sel"),
        ],
        [InlineKeyboardButton(text="نمایش نتایج", callback_data="fn:apply")],
        [InlineKeyboardButton(text="ارسال خلاصه با این فیلتر", callback_data="fn:filtered_send")],
        [InlineKeyboardButton(text="بازگشت", callback_data="p:news")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=btns)


@router.callback_query(F.data == "fn:menu")
async def cb_filter_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await is_auth(callback.from_user.id):
        return
    data = await state.get_data()
    if "time" not in data:
        await state.update_data(time="a", batch="a", sources=[], categories=[], page=0)
        data = await state.get_data()
    await safe_answer(callback)
    txt = await _get_filter_text(data)
    kb = _filter_menu_kb(data)
    try:
        await callback.message.edit_text(txt, reply_markup=kb)
    except:
        await callback.message.answer(txt, reply_markup=kb)
    await state.set_state(NewsFilter.menu)


@router.callback_query(F.data.startswith("fn:t:"))
async def cb_time_filter(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await is_auth(callback.from_user.id):
        return
    val = callback.data.split(":")[2]
    if val == "c":
        await safe_answer(callback)
        await callback.message.answer("بازه زمانی:\n\nمثال:\n2024-01-01 2024-01-31")
        await state.set_state(NewsFilter.custom_date)
        return
    await state.update_data(time=val, page=0)
    await safe_answer(callback, TIME_LABELS.get(val, val))
    data = await state.get_data()
    txt = await _get_filter_text(data)
    kb = _filter_menu_kb(data)
    try:
        await callback.message.edit_text(txt, reply_markup=kb)
    except:
        pass


@router.message(NewsFilter.custom_date)
async def cb_custom_date_input(message, state: FSMContext):
    if not message.from_user or not await is_auth(message.from_user.id):
        return
    try:
        parts = (message.text or "").strip().split()
        start = datetime.strptime(parts[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end = datetime.strptime(parts[1], "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
        await state.update_data(time="c", time_start=start.isoformat(), time_end=end.isoformat(), page=0)
        await message.answer(f"بازه: {parts[0]} تا {parts[1]}")
    except:
        await message.answer("فرمت: 2024-01-01 2024-01-31")
        return
    data = await state.get_data()
    txt = await _get_filter_text(data)
    kb = _filter_menu_kb(data)
    await message.answer(txt, reply_markup=kb)
    await state.set_state(NewsFilter.menu)


@router.callback_query(F.data.startswith("fn:b:"))
async def cb_batch_filter(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await is_auth(callback.from_user.id):
        return
    val = callback.data.split(":")[2]
    if val == "ask":
        await safe_answer(callback)
        await callback.message.answer("شماره دفعه:\n\nمثال: 3")
        await state.set_state(NewsFilter.batch_input)
        return
    await state.update_data(batch=val, page=0)
    await safe_answer(callback, BATCH_LABELS.get(val, val))
    data = await state.get_data()
    txt = await _get_filter_text(data)
    kb = _filter_menu_kb(data)
    try:
        await callback.message.edit_text(txt, reply_markup=kb)
    except:
        pass


@router.message(NewsFilter.batch_input)
async def cb_batch_input(message, state: FSMContext):
    if not message.from_user or not await is_auth(message.from_user.id):
        return
    try:
        n = int((message.text or "").strip())
        assert n > 0
    except:
        await message.answer("عدد مثبت بفرست.")
        return
    await state.update_data(batch=n, page=0)
    await message.answer(f"دفعه #{n}")
    data = await state.get_data()
    txt = await _get_filter_text(data)
    kb = _filter_menu_kb(data)
    await message.answer(txt, reply_markup=kb)
    await state.set_state(NewsFilter.menu)


@router.callback_query(F.data == "fn:s:all")
async def cb_src_all(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await is_auth(callback.from_user.id):
        return
    await state.update_data(sources=[], page=0)
    await safe_answer(callback, "همه منابع")
    data = await state.get_data()
    txt = await _get_filter_text(data)
    try:
        await callback.message.edit_text(txt, reply_markup=_filter_menu_kb(data))
    except:
        pass


@router.callback_query(F.data == "fn:s:sel")
async def cb_src_select(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await is_auth(callback.from_user.id):
        return
    data = await state.get_data()
    sel = set(data.get("sources", []))
    async with async_session_factory() as s:
        srcs = (await s.execute(select(Source).order_by(Source.id))).scalars().all()
    await safe_answer(callback)
    btns = []
    for src in srcs:
        em = SRC_EMOJI.get(src.type, "??")
        mark = "* " if src.id in sel else ""
        btns.append([InlineKeyboardButton(text=f"{mark}{em} {src.name}", callback_data=f"fns:{src.id}")])
    btns.append([
        InlineKeyboardButton(text="همه", callback_data="fns:all"),
        InlineKeyboardButton(text="هیچکدام", callback_data="fns:none"),
    ])
    btns.append([InlineKeyboardButton(text="تأیید انتخاب", callback_data="fn:menu")])
    try:
        await callback.message.edit_text("منابع رو انتخاب کن:", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))
    except:
        await callback.message.answer("منابع رو انتخاب کن:", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))


@router.callback_query(F.data.startswith("fns:"))
async def cb_src_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await is_auth(callback.from_user.id):
        return
    val = callback.data.split(":")[1]
    data = await state.get_data()
    sel = set(data.get("sources", []))
    if val == "all":
        async with async_session_factory() as s:
            srcs = (await s.execute(select(Source.id))).scalars().all()
        sel = set(srcs)
    elif val == "none":
        sel = set()
    else:
        sid = int(val)
        if sid in sel:
            sel.discard(sid)
        else:
            sel.add(sid)
    await state.update_data(sources=list(sel), page=0)
    await safe_answer(callback)
    async with async_session_factory() as s:
        srcs = (await s.execute(select(Source).order_by(Source.id))).scalars().all()
    btns = []
    for src in srcs:
        em = SRC_EMOJI.get(src.type, "??")
        mark = "* " if src.id in sel else ""
        btns.append([InlineKeyboardButton(text=f"{mark}{em} {src.name}", callback_data=f"fns:{src.id}")])
    btns.append([
        InlineKeyboardButton(text="همه", callback_data="fns:all"),
        InlineKeyboardButton(text="هیچکدام", callback_data="fns:none"),
    ])
    btns.append([InlineKeyboardButton(text=f"تأیید ({len(sel)} منبع)", callback_data="fn:menu")])
    try:
        await callback.message.edit_text(f"انتخاب منبع ({len(sel)} انتخاب شده):", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))
    except:
        pass


@router.callback_query(F.data == "fn:c:all")
async def cb_cat_all(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await is_auth(callback.from_user.id):
        return
    await state.update_data(categories=[], page=0)
    await safe_answer(callback, "همه موضوعات")
    data = await state.get_data()
    try:
        await callback.message.edit_text(await _get_filter_text(data), reply_markup=_filter_menu_kb(data))
    except:
        pass


@router.callback_query(F.data == "fn:c:sel")
async def cb_cat_select(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await is_auth(callback.from_user.id):
        return
    data = await state.get_data()
    sel = set(data.get("categories", []))
    await safe_answer(callback)
    btns = []
    for k, lb in CATS.items():
        mark = "* " if k in sel else ""
        btns.append([InlineKeyboardButton(text=f"{mark}{lb}", callback_data=f"fnc:{k}")])
    btns.append([InlineKeyboardButton(text="تأیید انتخاب", callback_data="fn:menu")])
    try:
        await callback.message.edit_text("موضوعات رو انتخاب کن:", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))
    except:
        await callback.message.answer("موضوعات:", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))


@router.callback_query(F.data.startswith("fnc:"))
async def cb_cat_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await is_auth(callback.from_user.id):
        return
    key = callback.data.split(":")[1]
    data = await state.get_data()
    sel = set(data.get("categories", []))
    if key in sel:
        sel.discard(key)
    else:
        sel.add(key)
    await state.update_data(categories=list(sel), page=0)
    await safe_answer(callback)
    btns = []
    for k, lb in CATS.items():
        mark = "* " if k in sel else ""
        btns.append([InlineKeyboardButton(text=f"{mark}{lb}", callback_data=f"fnc:{k}")])
    btns.append([InlineKeyboardButton(text=f"تأیید ({len(sel)} موضوع)", callback_data="fn:menu")])
    try:
        await callback.message.edit_text(f"موضوعات ({len(sel)} انتخاب شده):", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))
    except:
        pass


# ── QUERY BUILDER ──

async def _build_query(state_data: dict):
    now = datetime.now(timezone.utc)
    today_s = now.replace(hour=0, minute=0, second=0, microsecond=0)
    query = select(ContentItem).where(ContentItem.processed == True)
    count_q = select(sqlfunc.count(ContentItem.id)).where(ContentItem.processed == True)
    t = state_data.get("time", "a")
    if t == "t":
        query = query.where(ContentItem.created_at >= today_s)
        count_q = count_q.where(ContentItem.created_at >= today_s)
    elif t == "w":
        ws = today_s - timedelta(days=7)
        query = query.where(ContentItem.created_at >= ws)
        count_q = count_q.where(ContentItem.created_at >= ws)
    elif t == "m":
        ms = today_s - timedelta(days=30)
        query = query.where(ContentItem.created_at >= ms)
        count_q = count_q.where(ContentItem.created_at >= ms)
    elif t == "c":
        try:
            start = datetime.fromisoformat(state_data.get("time_start", ""))
            end = datetime.fromisoformat(state_data.get("time_end", ""))
            query = query.where(ContentItem.created_at >= start, ContentItem.created_at <= end)
            count_q = count_q.where(ContentItem.created_at >= start, ContentItem.created_at <= end)
        except:
            pass
    b = state_data.get("batch", "a")
    if b == "l":
        async with async_session_factory() as s:
            r = await s.execute(select(Setting.value).where(Setting.key == "current_batch"))
            cur = r.scalar_one_or_none()
            if cur:
                query = query.where(ContentItem.collection_batch == int(cur))
                count_q = count_q.where(ContentItem.collection_batch == int(cur))
    elif b != "a":
        try:
            bn = int(b)
            query = query.where(ContentItem.collection_batch == bn)
            count_q = count_q.where(ContentItem.collection_batch == bn)
        except:
            pass
    srcs = state_data.get("sources", [])
    if srcs:
        query = query.where(ContentItem.source_id.in_(srcs))
        count_q = count_q.where(ContentItem.source_id.in_(srcs))
    cats = state_data.get("categories", [])
    if cats:
        query = query.where(ContentItem.category.in_(cats))
        count_q = count_q.where(ContentItem.category.in_(cats))
    return query, count_q


# ── SEND PAGE ──

async def _send_page(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    pp = 5
    page = data.get("page", 0)
    off = page * pp
    query, count_q = await _build_query(data)
    async with async_session_factory() as s:
        total = (await s.execute(count_q)).scalar() or 0
        items = (await s.execute(query.order_by(ContentItem.created_at.desc()).offset(off).limit(pp))).scalars().all()
    if not items:
        btns = []
        if page > 0:
            btns.append([InlineKeyboardButton(text="قبلی", callback_data="fn:prev")])
        btns.append([
            InlineKeyboardButton(text="فیلتر", callback_data="fn:menu"),
            InlineKeyboardButton(text="جمع‌آوری", callback_data="fn:fetch"),
        ])
        await callback.message.answer("نتیجه‌ای یافت نشد!", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))
        return
    fl = await _get_filter_text(data)
    await callback.message.answer(f"{fl}\n\n{total} مطلب - صفحه {page + 1}\n------")
    for item in items:
        msg = format_single_item_html(item)
        raw = item.raw_text or item.title or ""
        fa = is_persian(raw)
        btns = []
        if fa:
            btns.append(InlineKeyboardButton(text="انگلیسی", callback_data=f"fni:tre:{item.id}"))
        else:
            btns.append(InlineKeyboardButton(text="فارسی", callback_data=f"fni:tfa:{item.id}"))
        btns.append(InlineKeyboardButton(text="متن", callback_data=f"fni:ful:{item.id}"))
        async with async_session_factory() as s:
            bm = (await s.execute(select(Bookmark).where(
                Bookmark.content_id == item.id, Bookmark.chat_id == callback.from_user.id
            ))).scalar_one_or_none()
        bm_text = "حذف مهم" if bm else "مهم"
        btns.append(InlineKeyboardButton(text=bm_text, callback_data=f"fni:bk:{item.id}"))
        try:
            await callback.message.answer(msg, disable_web_page_preview=False,
                                          reply_markup=InlineKeyboardMarkup(inline_keyboard=[btns]))
        except Exception as e:
            logger.error(f"Send filtered item: {e}")
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="قبلی", callback_data="fn:prev"))
    if len(items) == pp:
        nav.append(InlineKeyboardButton(text="بعدی", callback_data="fn:next"))
    btns_back = []
    if nav:
        btns_back.append(nav)
    btns_back.append([
        InlineKeyboardButton(text="فیلتر", callback_data="fn:menu"),
        InlineKeyboardButton(text="ارسال این‌ها", callback_data="fn:filtered_send"),
        InlineKeyboardButton(text="منو", callback_data="p:news"),
    ])
    await callback.message.answer("------", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns_back))


@router.callback_query(F.data == "fn:apply")
async def cb_apply(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await is_auth(callback.from_user.id):
        return
    await state.update_data(page=0)
    await safe_answer(callback)
    await _send_page(callback, state)


@router.callback_query(F.data == "fn:next")
async def cb_next(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await is_auth(callback.from_user.id):
        return
    data = await state.get_data()
    data["page"] = data.get("page", 0) + 1
    await state.update_data(**data)
    await safe_answer(callback)
    await _send_page(callback, state)


@router.callback_query(F.data == "fn:prev")
async def cb_prev(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await is_auth(callback.from_user.id):
        return
    data = await state.get_data()
    data["page"] = max(0, data.get("page", 0) - 1)
    await state.update_data(**data)
    await safe_answer(callback)
    await _send_page(callback, state)


@router.callback_query(F.data == "fn:filtered_send")
async def cb_filtered_send(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await is_auth(callback.from_user.id):
        return
    await safe_answer(callback, "Working...")
    async with async_session_factory() as s:
        rv = (await s.execute(select(Setting.value).where(Setting.key == "receiver_ids"))).scalar_one_or_none()
        try:
            rids = json.loads(rv) if rv else []
        except:
            rids = []
    if not rids:
        await callback.message.answer("No receivers!")
        return
    data = await state.get_data()
    query, _ = await _build_query(data)
    async with async_session_factory() as s:
        items = (await s.execute(query.order_by(ContentItem.score.desc()).limit(20))).scalars().all()
    if not items:
        await callback.message.answer("Nothing with this filter.")
        return
    header = f"Filtered summary\n{datetime.now().strftime('%Y-%m-%d')}\n\n{len(items)} items:\n------"
    sent = 0
    for cid in rids:
        try:
            await callback.bot.send_message(chat_id=cid, text=header)
            for item in items:
                msg = format_single_item_html(item)
                try:
                    await callback.bot.send_message(chat_id=cid, text=msg, disable_web_page_preview=False)
                except:
                    pass
            sent += 1
        except Exception as e:
            logger.error(f"Filtered send {cid}: {e}")
    await callback.message.answer(f"{len(items)} items sent to {sent}/{len(rids)}")


# ── ITEM ACTIONS ──

@router.callback_query(F.data.startswith("fni:tfa:"))
async def cb_tr_fa(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_auth(callback.from_user.id):
        return
    iid = int(callback.data.split(":")[2])
    await safe_answer(callback, "Translating to Farsi...")
    async with async_session_factory() as s:
        item = (await s.execute(select(ContentItem).where(ContentItem.id == iid))).scalar_one_or_none()
    if not item:
        await callback.message.answer("Not found.")
        return
    text = item.raw_text or item.title or ""
    if not text:
        await callback.message.answer("No text.")
        return
    from app.services.ai_service import ai_service
    tr = await ai_service.translate_to_farsi(text[:3000])
    async with async_session_factory() as s:
        db = (await s.execute(select(ContentItem).where(ContentItem.id == iid))).scalar_one_or_none()
        if db:
            db.translated_fa = tr
            await s.commit()
    msg = f"ترجمه فارسی:\n\n{h(item.title)}\n\n{h(tr[:2500])}"
    if item.url:
        msg += f'\n\n{item.url}'
    await callback.message.answer(msg, disable_web_page_preview=True)


@router.callback_query(F.data.startswith("fni:tre:"))
async def cb_tr_en(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_auth(callback.from_user.id):
        return
    iid = int(callback.data.split(":")[2])
    await safe_answer(callback, "Translating...")
    async with async_session_factory() as s:
        item = (await s.execute(select(ContentItem).where(ContentItem.id == iid))).scalar_one_or_none()
    if not item:
        await callback.message.answer("Not found.")
        return
    text = item.raw_text or item.title or ""
    if not text:
        await callback.message.answer("No text.")
        return
    from app.services.ai_service import ai_service
    tr = await ai_service.translate_to_english(text[:3000])
    msg = f"English:\n\n{h(item.title)}\n\n{h(tr[:2500])}"
    if item.url:
        msg += f'\n\n{item.url}'
    await callback.message.answer(msg, disable_web_page_preview=True)


@router.callback_query(F.data.startswith("fni:ful:"))
async def cb_full(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_auth(callback.from_user.id):
        return
    iid = int(callback.data.split(":")[2])
    await safe_answer(callback)
    async with async_session_factory() as s:
        item = (await s.execute(select(ContentItem).where(ContentItem.id == iid))).scalar_one_or_none()
    if not item:
        await callback.message.answer("Not found.")
        return
    full = item.raw_text or "No text."
    if len(full) > 3500:
        full = full[:3500] + "\n\n[...]"
    btns = []
    if is_persian(full):
        btns.append([InlineKeyboardButton(text="انگلیسی", callback_data=f"fni:tre:{item.id}")])
    else:
        btns.append([InlineKeyboardButton(text="فارسی", callback_data=f"fni:tfa:{item.id}")])
    await callback.message.answer(f"متن کامل:\n\n{h(full)}", disable_web_page_preview=True,
                                  reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))


@router.callback_query(F.data.startswith("fni:bk:"))
async def cb_bookmark(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_auth(callback.from_user.id):
        return
    iid = int(callback.data.split(":")[2])
    uid = callback.from_user.id
    async with async_session_factory() as s:
        existing = (await s.execute(select(Bookmark).where(
            Bookmark.content_id == iid, Bookmark.chat_id == uid
        ))).scalar_one_or_none()
        if existing:
            await s.delete(existing)
            await s.commit()
            await safe_answer(callback, "Removed from bookmarks")
        else:
            s.add(Bookmark(content_id=iid, chat_id=uid))
            await s.commit()
            await safe_answer(callback, "Bookmarked!")


@router.callback_query(F.data.startswith("fnbk:"))
async def cb_bookmarks(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_auth(callback.from_user.id):
        return
    page = int(callback.data.split(":")[1])
    pp = 5
    off = page * pp
    uid = callback.from_user.id
    async with async_session_factory() as s:
        total = (await s.execute(select(sqlfunc.count(Bookmark.id)).where(Bookmark.chat_id == uid))).scalar() or 0
        bms = (await s.execute(
            select(Bookmark).where(Bookmark.chat_id == uid).order_by(Bookmark.created_at.desc()).offset(off).limit(pp)
        )).scalars().all()
    await safe_answer(callback)
    if not bms:
        await callback.message.answer(
            "Bookmarks\n\nNo bookmarks yet.\nUse filter to bookmark items.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="فیلتر مطالب", callback_data="fn:menu")],
                [InlineKeyboardButton(text="بازگشت", callback_data="p:news")],
            ]),
        )
        return
    await callback.message.answer(f"Bookmarks ({total} items):")
    for bm in bms:
        async with async_session_factory() as s:
            item = (await s.execute(select(ContentItem).where(ContentItem.id == bm.content_id))).scalar_one_or_none()
        if not item:
            continue
        msg = format_single_item_html(item)
        raw = item.raw_text or item.title or ""
        fa = is_persian(raw)
        btns = []
        if fa:
            btns.append(InlineKeyboardButton(text="انگلیسی", callback_data=f"fni:tre:{item.id}"))
        else:
            btns.append(InlineKeyboardButton(text="فارسی", callback_data=f"fni:tfa:{item.id}"))
        btns.append(InlineKeyboardButton(text="متن", callback_data=f"fni:ful:{item.id}"))
        btns.append(InlineKeyboardButton(text="حذف", callback_data=f"fni:bk:{item.id}"))
        try:
            await callback.message.answer(msg, disable_web_page_preview=False,
                                          reply_markup=InlineKeyboardMarkup(inline_keyboard=[btns]))
        except:
            pass
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="PREV", callback_data=f"fnbk:{page - 1}"))
    if len(bms) == pp:
        nav.append(InlineKeyboardButton(text="NEXT", callback_data=f"fnbk:{page + 1}"))
    btns_b = []
    if nav:
        btns_b.append(nav)
    btns_b.append([InlineKeyboardButton(text="بازگشت", callback_data="p:news")])
    await callback.message.answer("------", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns_b))
