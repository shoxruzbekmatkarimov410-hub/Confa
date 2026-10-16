import asyncio
import time

from aiogram import Bot, F, Router
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.types import CallbackQuery, Message

import db
from config import CHANNEL_ID, MOD_CHAT_ID, OWNER_ID, PERM_BAN
from services import admin_panel_kb, publish, safe_send
from texts import t

HELP = (
    "📋 Admin buyruqlari:\n\n"
    "/admin — panel\n"
    "/stats — umumiy statistika\n"
    "/pending — kutilayotgan postlar\n"
    "/user <raqam> — foydalanuvchi ma'lumoti\n"
    "/ban <raqam> [soat] — ban (soat yozilmasa doimiy)\n"
    "/unban <raqam> — banni olib tashlash\n"
    "/delpost <№> — kanaldan postni o'chirish\n"
    "/words — taqiqlangan so'zlar\n"
    "/addword <so'z> | /delword <so'z>\n"
    "/broadcast <matn> — hammaga xabar\n"
    "/addadmin <tg_id> | /deladmin <tg_id> — faqat bosh admin"
)


class IsAdmin(BaseFilter):
    async def __call__(self, event) -> bool:
        return await db.is_admin(event.from_user.id)


router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


def num(s):
    try:
        return int(str(s).lstrip("#№"))
    except (ValueError, TypeError):
        return None


async def stats_text():
    s = await db.global_stats()
    return (f"📊 Statistika\n\n👥 Foydalanuvchilar: {s['users']}\n📨 24 soatda: {s['today']}\n"
            f"⏳ Kutilmoqda: {s['pending']}\n✅ Chop etilgan: {s['published']}\n"
            f"❌ Rad etilgan: {s['rejected']}\n🗑 O'chirilgan: {s['deleted']}")


async def pending_text():
    rows = await db.pending_posts()
    if not rows:
        return "🕓 Kutilayotgan post yo'q."
    return "🕓 Kutilayotgan postlar: " + ", ".join(f"№{r['id']}" for r in rows)


async def delete_published(bot: Bot, pid):
    post = await db.get_post(pid)
    if not post or post["status"] != "published":
        return False
    try:
        await bot.delete_message(CHANNEL_ID, post["channel_msg_id"])
    except Exception:
        pass
    await db.set_post(pid, status="deleted")
    return True


# ---------- moderation buttons ----------
@router.callback_query(F.data.startswith("mod:"))
async def moderate(c: CallbackQuery, bot: Bot):
    parts = c.data.split(":")
    action, pid = parts[1], int(parts[2])
    post = await db.get_post(pid)
    if not post or post["status"] != "pending":
        await c.answer("Allaqachon ko'rib chiqilgan", show_alert=True)
        return
    owner = await db.get_user_by_id(post["user_id"])
    lang = owner["lang"]
    who = c.from_user.full_name

    if action == "ok":
        try:
            mid = await publish(bot, post)
        except Exception as e:
            await c.answer(f"Kanalga yuborib bo'lmadi: {e}", show_alert=True)
            return
        await db.set_post(pid, status="published", channel_msg_id=mid, moderator=c.from_user.id)
        await safe_send(bot, owner["tg_id"], t(lang, "approved", id=pid))
        result = f"✅ №{pid} tasdiqlandi — {who}"
    else:
        reason = parts[3] if action == "no" else "other"
        await db.set_post(pid, status="rejected", reject_reason=reason, moderator=c.from_user.id)
        await safe_send(bot, owner["tg_id"],
                        t(lang, "rejected", id=pid, reason=t(lang, f"reason_{reason}")))
        result = f"❌ №{pid} rad etildi ({reason}) — {who}"
        if action == "ban":
            await db.ban(owner["id"], int(time.time()) + 86400)
            result += f"\n🚫 Anon #{owner['id']} 24 soatga bloklandi"

    await c.message.edit_reply_markup(reply_markup=None)
    await c.message.reply(result)
    await c.answer()


# ---------- panel buttons ----------
@router.callback_query(F.data.startswith("adm:"))
async def panel(c: CallbackQuery, bot: Bot):
    parts = c.data.split(":")
    act = parts[1]
    if act == "stats":
        await c.message.answer(await stats_text())
    elif act == "pending":
        await c.message.answer(await pending_text())
    elif act == "help":
        await c.message.answer(HELP)
    elif act == "delpost":
        ok = await delete_published(bot, int(parts[2]))
        await c.message.edit_reply_markup(reply_markup=None)
        await c.message.reply(f"🗑 №{parts[2]} o'chirildi" if ok else "Post topilmadi yoki allaqachon o'chirilgan")
    elif act == "ignore":
        await c.message.edit_reply_markup(reply_markup=None)
    await c.answer()


# ---------- commands ----------
@router.message(Command("admin"))
async def admin_cmd(m: Message):
    await m.answer("🛠 Admin panel\n\n" + await pending_text(), reply_markup=admin_panel_kb())


@router.message(Command("help_admin"))
async def help_cmd(m: Message):
    await m.answer(HELP)


@router.message(Command("stats"))
async def stats_cmd(m: Message):
    await m.answer(await stats_text())


@router.message(Command("pending"))
async def pending_cmd(m: Message):
    await m.answer(await pending_text())


@router.message(Command("user"))
async def user_cmd(m: Message, command: CommandObject):
    uid = num(command.args)
    user = await db.get_user_by_id(uid) if uid else None
    if not user:
        await m.answer("Ishlatish: /user <anon_raqam>")
        return
    s = await db.user_stats(user["id"])
    banned = "ha" if db.is_banned(user) else "yo'q"
    await m.answer(f"👤 Anon #{user['id']}\nTil: {user['lang']}\nBlok: {banned}\n"
                   f"Yuborgan: {s['total']} | chop: {s['published']} | rad: {s['rejected']} | "
                   f"o'chirilgan: {s['deleted']} | kutilmoqda: {s['pending']}")


@router.message(Command("ban"))
async def ban_cmd(m: Message, command: CommandObject, bot: Bot):
    a = (command.args or "").split()
    uid = num(a[0]) if a else None
    user = await db.get_user_by_id(uid) if uid else None
    if not user:
        await m.answer("Ishlatish: /ban <anon_raqam> [soat]")
        return
    hours = num(a[1]) if len(a) > 1 else None
    until = int(time.time() + hours * 3600) if hours else PERM_BAN
    await db.ban(user["id"], until)
    await safe_send(bot, user["tg_id"], t(user["lang"], "banned"))
    await m.answer(f"🚫 Anon #{user['id']} bloklandi" + (f" ({hours} soat)." if hours else " (doimiy)."))


@router.message(Command("unban"))
async def unban_cmd(m: Message, command: CommandObject):
    uid = num(command.args)
    user = await db.get_user_by_id(uid) if uid else None
    if not user:
        await m.answer("Ishlatish: /unban <anon_raqam>")
        return
    await db.ban(user["id"], 0)
    await m.answer(f"✅ Anon #{user['id']} blokdan chiqarildi.")


@router.message(Command("delpost"))
async def delpost_cmd(m: Message, command: CommandObject, bot: Bot):
    pid = num(command.args)
    if not pid:
        await m.answer("Ishlatish: /delpost <№>")
        return
    ok = await delete_published(bot, pid)
    await m.answer(f"🗑 №{pid} o'chirildi." if ok else "Post topilmadi yoki chop etilmagan.")


@router.message(Command("words"))
async def words_cmd(m: Message):
    w = await db.badwords()
    await m.answer("🚫 Taqiqlangan so'zlar:\n" + (", ".join(w) if w else "(bo'sh)"))


@router.message(Command("addword"))
async def addword_cmd(m: Message, command: CommandObject):
    if not command.args:
        await m.answer("Ishlatish: /addword <so'z>")
        return
    await db.add_word(command.args.strip())
    await m.answer("✅ Qo'shildi.")


@router.message(Command("delword"))
async def delword_cmd(m: Message, command: CommandObject):
    if not command.args:
        await m.answer("Ishlatish: /delword <so'z>")
        return
    await db.del_word(command.args.strip())
    await m.answer("✅ O'chirildi.")


@router.message(Command("addadmin"))
async def addadmin_cmd(m: Message, command: CommandObject):
    if m.from_user.id != OWNER_ID:
        await m.answer("Faqat bosh admin.")
        return
    tg = num(command.args)
    if not tg:
        await m.answer("Ishlatish: /addadmin <tg_id>")
        return
    await db.add_admin(tg)
    await m.answer("✅ Admin qo'shildi.")


@router.message(Command("deladmin"))
async def deladmin_cmd(m: Message, command: CommandObject):
    if m.from_user.id != OWNER_ID:
        await m.answer("Faqat bosh admin.")
        return
    tg = num(command.args)
    if not tg:
        await m.answer("Ishlatish: /deladmin <tg_id>")
        return
    await db.del_admin(tg)
    await m.answer("✅ Admin o'chirildi.")


@router.message(Command("broadcast"))
async def broadcast_cmd(m: Message, command: CommandObject, bot: Bot):
    if not command.args:
        await m.answer("Ishlatish: /broadcast <matn>")
        return
    users = await db.all_users()
    ok = 0
    for u in users:
        if await safe_send(bot, u["tg_id"], command.args):
            ok += 1
        await asyncio.sleep(0.05)
    await m.answer(f"📣 Yuborildi: {ok}/{len(users)}")
