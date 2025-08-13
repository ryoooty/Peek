from __future__ import annotations

from typing import Any, Dict, Callable, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from app import storage


class BanMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject | Update, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject | Update,
        data: Dict[str, Any],
    ) -> Any:
        from_user = data.get("event_from_user") or getattr(event, "from_user", None)
        if from_user:
            u = storage.get_user(from_user.id)
            if u and u.get("banned"):
                answer = getattr(event, "answer", None)
                if callable(answer):
                    await answer("Доступ ограничен.")
                else:
                    bot = data.get("bot")
                    if bot:
                        await bot.send_message(from_user.id, "Доступ ограничен.")
                return
        return await handler(event, data)
