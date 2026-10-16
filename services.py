import logging
import re

from aiogram import Bot
from aiogram.types import (InlineKeyboardButton, InlineKeyboardMarkup,
                           KeyboardButton, ReplyKeyboardMarkup)

from config import CHANNEL_ID
from texts import t

log = logging.getLogger(__name__)

TAGS = {"general": "#umumiy", "question": "#savol", "love": "#sevgi",
        "advice": "#maslahat", "announce": "#elon"}

URL_RE = re.compile(r"(https?://|www\.|t\.me/|\b[\w-]+\.(?:com|ru|uz|org|net|me|io|info)\b)", re.I)
USERNAME_RE = re.compile(r"@\w{3,}")
PHONE_RE = re.compile(r"(?:\+?\d[\s\-()]?){9,}")


def check_text(text, badwords):
    """Returns filter key (link/username/phone/badword) or None."""
    if URL_RE.search(text):
        return "link"
    if USERNAME_RE.search(text):
        return "username"
    if PHONE_RE.search(text):
        return "phone"
    low = text.lower()
    for w in badwords:
        if w and w in low:
            return "badword"
    return None


# ---------- keyboards ----------
def _ib(text, data):
    return InlineKeyboardButton(text=text, callback_data=data)


def main_menu(lang):
    return ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
        [KeyboardButton(text=t(lang, "btn_write"))],
        [KeyboardButton(text=t(lang, "btn_my")), KeyboardButton(text=t(lang, "btn_stats"))],
        [KeyboardButton(text=t(lang, "btn_rules")), KeyboardButton(text=t(lang, "btn_lang"))],
    ])


def lang_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        _ib("🇺🇿 O'zbekcha", "lang:uz"), _ib("🇷🇺 Русский", "lang:ru"), _ib("🇬🇧 English", "lang:en")]])


def cats_kb(lang):
    cats = list(TAGS)
    rows = [[_ib(t(lang, f"cat_{c}"), f"cat:{c}")] for c in cats]
    rows.append([_ib(t(lang, "cancel"), "cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_kb(lang):
    return InlineKeyboardMarkup(inline_keyboard=[[_ib(t(lang, "cancel"), "cancel")]])


def my_posts_kb(posts):
    return InlineKeyboardMarkup(inline_keyboard=[[_ib(f"🗑 №{p['id']}", f"del:{p['id']}")] for p in posts])


def mod_kb(pid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ib("✅ Tasdiqlash", f"mod:ok:{pid}")],
        [_ib("📢 Reklama", f"mod:no:{pid}:ad"), _ib("🤬 Haqorat", f"mod:no:{pid}:insult")],
        [_ib("🔒 Shaxsiy", f"mod:no:{pid}:personal"), _ib("❓ Boshqa", f"mod:no:{pid}:other")],
        [_ib("🚫 Rad etish + 24 soat ban", f"mod:ban:{pid}")],
    ])


def report_kb(pid):
    return InlineKeyboardMarkup(inline_keyboard=[[
        _ib("🗑 Postni o'chirish", f"adm:delpost:{pid}"), _ib("E'tiborsiz", "adm:ignore")]])


def admin_panel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [_ib("📊 Statistika", "adm:stats"), _ib("🕓 Kutilayotganlar", "adm:pending")],
        [_ib("📋 Buyruqlar", "adm:help")]])


def channel_kb(username, pid, lang="uz"):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(lang, "btn_write_ch"), url=f"https://t.me/{username}"),
        InlineKeyboardButton(text=t(lang, "btn_report_ch"), url=f"https://t.me/{username}?start=report_{pid}"),
    ]])


# ---------- sending ----------
async def send_content(bot: Bot, chat_id, post, text, kb=None):
    ctype = post["ctype"]
    if ctype == "photo":
        return await bot.send_photo(chat_id, post["file_id"], caption=text, reply_markup=kb)
    if ctype == "voice":
        return await bot.send_voice(chat_id, post["file_id"], caption=text, reply_markup=kb)
    return await bot.send_message(chat_id, text, reply_markup=kb)


async def publish(bot: Bot, post):
    username = (await bot.me()).username
    text = f"{post['text'] or ''}\n\n{TAGS.get(post['category'], '#umumiy')}\n№{post['id']}".strip()
    msg = await send_content(bot, CHANNEL_ID, post, text, channel_kb(username, post["id"]))
    return msg.message_id


async def safe_send(bot: Bot, chat_id, text, **kw):
    try:
        await bot.send_message(chat_id, text, **kw)
        return True
    except Exception as e:  # user blocked the bot, etc.
        log.warning("send failed to %s: %s", chat_id, e)
        return False
