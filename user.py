import time

from aiogram import Bot, F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import db
from config import CHANNEL_ID, COOLDOWN_SEC, DAILY_LIMIT, MAX_LEN, MOD_CHAT_ID
from services import (TAGS, cancel_kb, cats_kb, check_text, lang_kb, main_menu,
                      mod_kb, my_posts_kb, report_kb, send_content)
from texts import all_texts, t

router = Router()
router.message.filter(F.chat.type == "private")


class Write(StatesGroup):
    content = State()


async def get_or_ask(m: Message):
    user = await db.get_user(m.from_user.id)
    if not user:
        await m.answer(t("uz", "choose_lang"), reply_markup=lang_kb())
    return user


# ---------- start / language ----------
@router.message(CommandStart())
async def start(m: Message, command: CommandObject, state: FSMContext):
    await state.clear()
    user = await db.get_user(m.from_user.id)
    if not user:
        await m.answer(t("uz", "choose_lang"), reply_markup=lang_kb())
        return
    if command.args and command.args.startswith("report_"):
        await handle_report(m, user, command.args[7:])
        return
    await m.answer(t(user["lang"], "welcome", n=user["id"]), reply_markup=main_menu(user["lang"]))


@router.callback_query(F.data.startswith("lang:"))
async def pick_lang(c: CallbackQuery):
    lang = c.data.split(":")[1]
    user = await db.get_user(c.from_user.id)
    if user:
        await db.set_lang(c.from_user.id, lang)
        text = t(lang, "lang_set")
    else:
        user = await db.create_user(c.from_user.id, lang)
        text = t(lang, "welcome", n=user["id"])
    try:
        await c.message.delete()
    except Exception:
        pass
    await c.message.answer(text, reply_markup=main_menu(lang))
    await c.answer()


@router.message(F.text.in_(all_texts("btn_lang")))
async def change_lang(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(t("uz", "choose_lang"), reply_markup=lang_kb())


# ---------- menu ----------
@router.message(F.text.in_(all_texts("btn_rules")))
async def rules(m: Message, state: FSMContext):
    await state.clear()
    user = await get_or_ask(m)
    if user:
        await m.answer(t(user["lang"], "rules"))


@router.message(F.text.in_(all_texts("btn_stats")))
async def stats(m: Message, state: FSMContext):
    await state.clear()
    user = await get_or_ask(m)
    if user:
        s = await db.user_stats(user["id"])
        await m.answer(t(user["lang"], "stats", **s))


@router.message(F.text.in_(all_texts("btn_my")))
async def my_posts(m: Message, state: FSMContext):
    await state.clear()
    user = await get_or_ask(m)
    if not user:
        return
    posts = await db.published_by_user(user["id"])
    if not posts:
        await m.answer(t(user["lang"], "no_posts"))
        return
    await m.answer(t(user["lang"], "my_title"), reply_markup=my_posts_kb(posts))


@router.callback_query(F.data.startswith("del:"))
async def delete_own(c: CallbackQuery, bot: Bot):
    user = await db.get_user(c.from_user.id)
    post = await db.get_post(int(c.data.split(":")[1]))
    if not user or not post or post["user_id"] != user["id"] or post["status"] != "published":
        await c.answer()
        return
    try:
        await bot.delete_message(CHANNEL_ID, post["channel_msg_id"])
    except Exception:
        pass
    await db.set_post(post["id"], status="deleted")
    await c.message.answer(t(user["lang"], "deleted", id=post["id"]))
    await c.answer()


# ---------- writing a post ----------
@router.message(F.text.in_(all_texts("btn_write")))
async def write(m: Message, state: FSMContext):
    await state.clear()
    user = await get_or_ask(m)
    if not user:
        return
    lang = user["lang"]
    if db.is_banned(user):
        await m.answer(t(lang, "banned"))
        return
    if await db.posts_last_day(user["id"]) >= DAILY_LIMIT:
        await m.answer(t(lang, "limit", n=DAILY_LIMIT))
        return
    wait = COOLDOWN_SEC - (time.time() - await db.last_post_time(user["id"]))
    if wait > 0:
        await m.answer(t(lang, "cooldown", s=int(wait) + 1))
        return
    await m.answer(t(lang, "choose_cat"), reply_markup=cats_kb(lang))


@router.callback_query(F.data.startswith("cat:"))
async def pick_cat(c: CallbackQuery, state: FSMContext):
    user = await db.get_user(c.from_user.id)
    if not user:
        await c.answer()
        return
    cat = c.data[4:]
    if cat not in TAGS:
        await c.answer()
        return
    await state.set_state(Write.content)
    await state.update_data(cat=cat)
    await c.message.edit_text(t(user["lang"], "ask_post", max=MAX_LEN), reply_markup=cancel_kb(user["lang"]))
    await c.answer()


@router.callback_query(F.data == "cancel")
async def cancel(c: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await db.get_user(c.from_user.id)
    await c.message.edit_text(t(user["lang"] if user else "uz", "cancelled"))
    await c.answer()


@router.message(Write.content, F.content_type.in_({"text", "photo", "voice"}))
async def got_post(m: Message, state: FSMContext, bot: Bot):
    user = await db.get_user(m.from_user.id)
    if not user:
        return
    lang = user["lang"]
    if db.is_banned(user):
        await state.clear()
        await m.answer(t(lang, "banned"))
        return
    text = (m.text or m.caption or "").strip()
    if len(text) > MAX_LEN:
        await m.answer(t(lang, "too_long", max=MAX_LEN))
        return
    bad = check_text(text, await db.badwords())
    if bad:
        await m.answer("⚠️ " + t(lang, f"filt_{bad}"))
        return

    ctype = m.content_type.value
    file_id = None
    if ctype == "photo":
        file_id = m.photo[-1].file_id
    elif ctype == "voice":
        file_id = m.voice.file_id

    data = await state.get_data()
    cat = data.get("cat", "general")
    pid = await db.create_post(user["id"], cat, ctype, file_id, text)
    post = await db.get_post(pid)
    await state.clear()

    head = f"📝 №{pid} | Anon #{user['id']} | {TAGS[cat]}\n\n"
    await send_content(bot, MOD_CHAT_ID, post, head + text, mod_kb(pid))
    await m.answer(t(lang, "sent", id=pid), reply_markup=main_menu(lang))


@router.message(Write.content)
async def unsupported(m: Message):
    user = await db.get_user(m.from_user.id)
    await m.answer(t(user["lang"] if user else "uz", "unsupported"))


# ---------- report (deep link from channel button) ----------
async def handle_report(m: Message, user, arg):
    try:
        pid = int(arg)
    except ValueError:
        return
    post = await db.get_post(pid)
    if not post or post["status"] != "published":
        return
    if await db.add_report(pid, m.from_user.id):
        cnt = await db.report_count(pid)
        await m.bot.send_message(MOD_CHAT_ID, f"🚩 №{pid} postiga shikoyat (jami: {cnt})",
                                 reply_markup=report_kb(pid))
    await m.answer(t(user["lang"], "report_sent"), reply_markup=main_menu(user["lang"]))


# ---------- fallback ----------
@router.message()
async def fallback(m: Message):
    user = await get_or_ask(m)
    if user:
        await m.answer(t(user["lang"], "menu_hint"), reply_markup=main_menu(user["lang"]))
