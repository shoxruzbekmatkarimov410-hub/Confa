import html
import logging
import re

from aiogram import Bot
from aiogram.types import (InlineKeyboardButton, InlineKeyboardMarkup,
                           KeyboardButton, ReplyKeyboardMarkup)

from config import BLOCK_LINKS, BLOCK_PHONES, BLOCK_USERNAMES, CHANNEL_ID
from texts import t

log = logging.getLogger(__name__)

TAGS = {"general": "#umumiy", "question": "#savol", "love": "#sevgi",
        "advice": "#maslahat", "announce": "#elon"}

URL_RE = re.compile(r"(https?://|www\.|t\.me/|\b[\w-]+\.(?:com|ru|uz|org|net|me|io|info)\b)", re.I)
USERNAME_RE = re.compile(r"@\w{3,}")
PHONE_RE = re.compile(r"(?:\+?\d[\s\-()]?){9,}")


def detect(text):
    """Postda nima borligini aniqlaydi (admin ogohlantirishi uchun)."""
    found = []
    if URL_RE.search(text):
        found.append("link")
    if USERNAME_RE.search(text):
        found.append("username")
    if PHONE_RE.search(text):
        found.append("phone")
    return found


def check_text(text, badwords):
    """Avto-rad etiladigan sabab (link/username/phone/badword) yoki None."""
    found = detect(text)
    if "link" in found and BLOCK_LINKS:
        return "link"
    if "username" in found and BLOCK_USERNAMES:
        return "username"
    if "phone" in found and BLOCK_PHONES:
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
async def send_content(bot: Bot, chat_id, post, text, kb=None, parse_mode=None):
    ctype = post["ctype"]
    if ctype == "photo":
        return await bot.send_photo(chat_id, post["file_id"], caption=text, reply_markup=kb, parse_mode=parse_mode)
    if ctype == "voice":
        return await bot.send_voice(chat_id, post["file_id"], caption=text, reply_markup=kb, parse_mode=parse_mode)
    return await bot.send_message(chat_id, text, reply_markup=kb, parse_mode=parse_mode)


async def publish(bot: Bot, post):
    """Kanalga chiqarish. Tugmalar inline emas, matn ichidagi havolalar:
    shunda Telegram 'Fikr bildirish' tugmasini ham ko'rsatadi."""
    username = (await bot.me()).username
    body = html.escape(post["text"] or "")
    links = (f'<a href="https://t.me/{username}">{t("uz", "btn_write_ch")}</a>  •  '
             f'<a href="https://t.me/{username}?start=report_{post["id"]}">{t("uz", "btn_report_ch")}</a>')
    text = f"{body}\n\n{TAGS.get(post['category'], '#umumiy')}\n№{post['id']}\n\n{links}".strip()
    msg = await send_content(bot, CHANNEL_ID, post, text, None, parse_mode="HTML")
    return msg.message_id


async def safe_send(bot: Bot, chat_id, text, **kw):
    try:
        await bot.send_message(chat_id, text, **kw)
        return True
    except Exception as e:  # user blocked the bot, etc.
        log.warning("send failed to %s: %s", chat_id, e)
        return False
