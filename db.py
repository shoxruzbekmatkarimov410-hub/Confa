import asyncio
import time
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import asyncpg

from config import DATABASE_URL, OWNER_ID

_pool = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id SERIAL PRIMARY KEY,
  tg_id BIGINT UNIQUE NOT NULL,
  lang TEXT NOT NULL DEFAULT 'uz',
  banned_until BIGINT NOT NULL DEFAULT 0,
  created_at BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS posts(
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL,
  category TEXT NOT NULL,
  ctype TEXT NOT NULL,
  file_id TEXT,
  text TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  channel_msg_id BIGINT,
  reject_reason TEXT,
  moderator BIGINT,
  created_at BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS admins(tg_id BIGINT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS badwords(word TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS reports(
  post_id INTEGER NOT NULL,
  tg_id BIGINT NOT NULL,
  created_at BIGINT NOT NULL,
  PRIMARY KEY(post_id, tg_id)
);
"""


def _clean_dsn(url):
    """Neon URL ichidagi sslmode/channel_binding asyncpg'ga to'g'ri kelmaydi."""
    p = urlparse(url)
    q = [(k, v) for k, v in parse_qsl(p.query) if k not in ("sslmode", "channel_binding")]
    return urlunparse(p._replace(query=urlencode(q)))


async def init():
    global _pool
    _pool = await asyncpg.create_pool(
        _clean_dsn(DATABASE_URL),
        ssl="require",
        min_size=1,
        max_size=5,
        statement_cache_size=0,               # Neon pooler (pgbouncer) bilan ishlashi uchun
        max_inactive_connection_lifetime=120,  # Neon bo'sh ulanishni yopadi
        command_timeout=30,
    )
    async with _pool.acquire() as c:
        await c.execute(SCHEMA)


async def _with_conn(fn):
    for attempt in range(3):
        try:
            async with _pool.acquire() as c:
                return await fn(c)
        except (asyncpg.PostgresConnectionError, asyncpg.InterfaceError, OSError):
            if attempt == 2:
                raise
            await asyncio.sleep(1)  # Neon uyg'onishi uchun


async def one(sql, *args):
    async def f(c):
        r = await c.fetchrow(sql, *args)
        return dict(r) if r else None
    return await _with_conn(f)


async def many(sql, *args):
    async def f(c):
        return [dict(r) for r in await c.fetch(sql, *args)]
    return await _with_conn(f)


async def val(sql, *args):
    async def f(c):
        return await c.fetchval(sql, *args)
    return await _with_conn(f)


async def execute(sql, *args):
    async def f(c):
        return await c.execute(sql, *args)
    return await _with_conn(f)


# ---------- users ----------
async def get_user(tg_id):
    return await one("SELECT * FROM users WHERE tg_id=$1", tg_id)


async def get_user_by_id(uid):
    return await one("SELECT * FROM users WHERE id=$1", uid)


async def create_user(tg_id, lang):
    await execute("INSERT INTO users(tg_id,lang,created_at) VALUES($1,$2,$3) "
                  "ON CONFLICT (tg_id) DO NOTHING", tg_id, lang, int(time.time()))
    return await get_user(tg_id)


async def set_lang(tg_id, lang):
    await execute("UPDATE users SET lang=$1 WHERE tg_id=$2", lang, tg_id)


def is_banned(user):
    return user["banned_until"] > time.time()


async def ban(uid, until):
    await execute("UPDATE users SET banned_until=$1 WHERE id=$2", until, uid)


async def all_users():
    return await many("SELECT * FROM users")


# ---------- posts ----------
async def create_post(user_id, category, ctype, file_id, text):
    return await val(
        "INSERT INTO posts(user_id,category,ctype,file_id,text,created_at) "
        "VALUES($1,$2,$3,$4,$5,$6) RETURNING id",
        user_id, category, ctype, file_id, text, int(time.time()))


async def get_post(pid):
    return await one("SELECT * FROM posts WHERE id=$1", pid)


async def set_post(pid, **fields):
    keys = list(fields)
    sets = ",".join(f"{k}=${i + 1}" for i, k in enumerate(keys))
    sql = f"UPDATE posts SET {sets} WHERE id=${len(keys) + 1}"
    await execute(sql, *[fields[k] for k in keys], pid)


async def posts_last_day(uid):
    return await val("SELECT COUNT(*) FROM posts WHERE user_id=$1 AND created_at>$2",
                     uid, int(time.time()) - 86400)


async def last_post_time(uid):
    return await val("SELECT MAX(created_at) FROM posts WHERE user_id=$1", uid) or 0


async def user_stats(uid):
    rows = await many("SELECT status, COUNT(*) AS c FROM posts WHERE user_id=$1 GROUP BY status", uid)
    s = {"pending": 0, "published": 0, "rejected": 0, "deleted": 0}
    for r in rows:
        s[r["status"]] = r["c"]
    s["total"] = sum(s.values())
    return s


async def pending_posts():
    return await many("SELECT id, user_id FROM posts WHERE status='pending' ORDER BY id")


async def published_by_user(uid, limit=5):
    return await many(
        "SELECT * FROM posts WHERE user_id=$1 AND status='published' ORDER BY id DESC LIMIT $2",
        uid, limit)


async def global_stats():
    users = await val("SELECT COUNT(*) FROM users")
    rows = await many("SELECT status, COUNT(*) AS c FROM posts GROUP BY status")
    s = {"pending": 0, "published": 0, "rejected": 0, "deleted": 0}
    for r in rows:
        s[r["status"]] = r["c"]
    today = await val("SELECT COUNT(*) FROM posts WHERE created_at>$1", int(time.time()) - 86400)
    return {"users": users, "today": today, **s}


# ---------- reports ----------
async def add_report(pid, tg_id):
    """True agar yangi shikoyat bo'lsa (bir odam bir postga bitta)."""
    res = await execute("INSERT INTO reports(post_id,tg_id,created_at) VALUES($1,$2,$3) "
                        "ON CONFLICT DO NOTHING", pid, tg_id, int(time.time()))
    return res.endswith(" 1")


async def report_count(pid):
    return await val("SELECT COUNT(*) FROM reports WHERE post_id=$1", pid)


# ---------- admins ----------
async def is_admin(tg_id):
    if tg_id == OWNER_ID:
        return True
    return await val("SELECT 1 FROM admins WHERE tg_id=$1", tg_id) is not None


async def add_admin(tg_id):
    await execute("INSERT INTO admins(tg_id) VALUES($1) ON CONFLICT DO NOTHING", tg_id)


async def del_admin(tg_id):
    await execute("DELETE FROM admins WHERE tg_id=$1", tg_id)


# ---------- badwords ----------
async def badwords():
    return [r["word"] for r in await many("SELECT word FROM badwords")]


async def add_word(w):
    await execute("INSERT INTO badwords(word) VALUES($1) ON CONFLICT DO NOTHING", w.lower())


async def del_word(w):
    await execute("DELETE FROM badwords WHERE word=$1", w.lower())
