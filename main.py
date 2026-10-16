import asyncio
import logging
import os

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

import admin
import db
import user
from config import BOT_TOKEN


async def health(request):
    return web.Response(text="ok")


async def start_web():
    """Render 'Web Service' port ochiq bo'lishini talab qiladi."""
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", "10000")))
    await site.start()


async def main():
    logging.basicConfig(level=logging.INFO)
    await db.init()
    await start_web()
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(admin.router)  # admin buyruqlari birinchi
    dp.include_router(user.router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
