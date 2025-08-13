from __future__ import annotations

from typing import Any, Dict, Callable, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import Message

from app import storage

class BanMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]], event: Message, data: Dict[str, Any]) -> Any:
        if event.from_user:
            u = storage.get_user(event.from_user.id)
            if u and u.get("banned"):
                return await event.answer("Доступ ограничен.")
        return await handler(event, data)
