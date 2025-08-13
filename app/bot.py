
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from app.mw.maintenance import MaintenanceMiddleware
from app.config import settings, register_reload_hook
from app import storage
# bot.py, в main() после создания bot и dp
from app import scheduler


# Routers (подключаем команды и меню раньше, чат — последним)


from app.handlers import admin as admin_handlers
from app.handlers import broadcast as broadcast_handlers
from app.handlers import user as user_handlers
from app.handlers import characters as characters_handlers
from app.handlers import profile as profile_handlers
from app.handlers import balance as balance_handlers
from app.handlers import chats as chats_handlers  # <- чат-обработчики ДОЛЖНЫ идти последними


# Если используете подписочный гейт, импортируйте из вашего модуля:
try:
    from app.middlewares.subscription import SubscriptionGateMiddleware
except Exception:
    SubscriptionGateMiddleware = None  # опционально

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


async def _set_bot_commands(bot: Bot) -> None:
    cmds = [
        BotCommand(command="start", description="Начать"),
        BotCommand(command="profile", description="Профиль"),
        BotCommand(command="characters", description="Персонажи"),
        BotCommand(command="chats", description="Мои чаты"),
        BotCommand(command="balance", description="Баланс"),
        BotCommand(command="reload", description="Перезагрузить конфиг (админ)"),
        BotCommand(command="maintenance", description="Режим техработ (админ)"),
    ]
    try:
        await bot.set_my_commands(cmds)
    except Exception:
        logging.exception("set_my_commands failed")


async def main():
    logging.info(">> Bot is starting…")

    # БД и бота
    storage.init(settings.db_path)
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()

    # Middlewares (внешние)
    dp.update.outer_middleware(MaintenanceMiddleware())
    if SubscriptionGateMiddleware:
        dp.update.outer_middleware(SubscriptionGateMiddleware())
    dp.update.outer_middleware(MaintenanceMiddleware())
    # Подключаем роутеры. ВАЖНО: «chats» — ПОСЛЕДНИЙ, чтобы не перехватывать slash-команды.
    dp.include_router(admin_handlers.router)
    dp.include_router(broadcast_handlers.router)
    dp.include_router(user_handlers.router)        # /start, главное меню
    dp.include_router(characters_handlers.router)  # карточки персонажей
    dp.include_router(profile_handlers.router)     # профиль/настройки
    dp.include_router(balance_handlers.router)     # баланс, промо, (оплата при необходимости)
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
        (Path("run") / "main.pid").write_text(str(Path("run").absolute()))
    except Exception:
        pass

    try:
        await dp.start_polling(bot)
    finally:
        logging.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
