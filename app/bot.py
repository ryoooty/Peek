
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from app.mw.maintenance import MaintenanceMiddleware
from app.mw.ban import BanMiddleware
from app.mw.chat_delay import ChatDelayMiddleware
from app.mw.rate_limit import RateLimitLLM
from app.config import settings, register_reload_hook
from app import storage
# bot.py, в main() после создания bot и dp
from app import scheduler, runtime




# Routers (подключаем команды и меню раньше, чат — последн
from app.handlers import admin as admin_handlers
from app.handlers import broadcast as broadcast_handlers
from app.handlers import system as system_handlers
from app.handlers import user as user_handlers
from app.handlers import characters as characters_handlers
from app.handlers import profile as profile_handlers
from app.handlers import balance as balance_handlers
from app.handlers import payments as payments_handlers
from app.handlers import chats as chats_handlers  # <- чат-обработчики ДОЛЖНЫ идти последними
from app.middlewares.subscription import SubscriptionGateMiddleware
from app.middlewares.timezone import TimezoneMiddleware
from aiohttp import web

runtime.setup_logging()

async def _run_http_server() -> None:
    app = web.Application()
    app.add_routes(payments_handlers.http_router)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, port=8080)
    await site.start()
    logger.info("HTTP server started on http://localhost:8080")
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()

async def _set_bot_commands(bot: Bot) -> None:
    cmds = [
        BotCommand(command="start", description="Начать"),
        BotCommand(command="profile", description="Профиль"),
        BotCommand(command="characters", description="Персонажи"),
        BotCommand(command="chats", description="Мои чаты"),
        BotCommand(command="balance", description="Токи"),
        BotCommand(command="reload", description="Перезагрузить конфиг (админ)"),
        BotCommand(command="maintenance", description="Режим техработ (админ)"),
    ]
    try:
        await bot.set_my_commands(cmds)
    except Exception:
        logging.exception("set_my_commands failed")


async def main():
    logging.info(">> Bot is starting…")

    if not settings.deepseek_api_key:
        logger.error("DEEPSEEK_API_KEY is not set")
        sys.exit(1)

    try:
        import aiohttp  # noqa: F401
    except Exception:
        logger.error("aiohttp is not installed")
        sys.exit(1)

    # БД и бота
    storage.init(settings.db_path)
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=MemoryStorage())

    rate_limit_mw = RateLimitLLM()
    # Middlewares (внешние)
    dp.update.outer_middleware(MaintenanceMiddleware())
    dp.update.outer_middleware(SubscriptionGateMiddleware())
    dp.update.outer_middleware(TimezoneMiddleware())
    dp.update.outer_middleware(BanMiddleware())
    dp.update.outer_middleware(ChatDelayMiddleware())

    dp.update.outer_middleware(rate_limit_mw)

    # Подключаем роутеры. ВАЖНО: «chats» — ПОСЛЕДНИЙ, чтобы не перехватывать slash-команды.
    dp.include_router(admin_handlers.router)
    dp.include_router(broadcast_handlers.router)
    dp.include_router(system_handlers.router)
    dp.include_router(user_handlers.router)        # /start, главное меню
    dp.include_router(characters_handlers.router)  # карточки персонажей

    dp.include_router(profile_handlers.router)     # профиль/настройки
    dp.include_router(balance_handlers.router)     # баланс, промо, (оплата при необходимости)
    dp.include_router(payments_handlers.router)    # оплаты и заявки
      # админ-команды
    dp.include_router(chats_handlers.router)       # чат-логика и LLM — ПОСЛЕДНИМ!
    
    await _set_bot_commands(bot)    
    scheduler.init(bot)
    # /reload — перезагрузка команд и горячие значения
    def _on_reload(_settings):
        asyncio.create_task(_set_bot_commands(bot))
        logging.info("Reload hook applied")
    register_reload_hook(_on_reload)

    # run/
    try:
        Path("run").mkdir(exist_ok=True)
        (Path("run") / "main.pid").write_text(str(os.getpid()))
    except Exception:
        logger.exception("failed to write pid file")

    try:
        await asyncio.gather(
            dp.start_polling(bot),
            _run_http_server(),
        )
    finally:
        logging.info("Bot stopped")
        await rate_limit_mw.shutdown()
        scheduler.shutdown()
        storage.close()



if __name__ == "__main__":
    asyncio.run(main())
