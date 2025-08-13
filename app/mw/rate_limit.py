from __future__ import annotations

import time
from typing import Any, Dict, Callable, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

class RateLimitLLM(BaseMiddleware):
    """Простой RL: не троттлим команды (/...), только обычные сообщения."""
    def __init__(self, rate_seconds: int = 3):
        self.rate = max(0, int(rate_seconds))
        self.last: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not self.rate:
            return await handler(event, data)
        text = getattr(event, "text", None)
        if text and text.startswith("/"):
            return await handler(event, data)  # команды не троттлим
        from_user = data.get("event_from_user") or getattr(event, "from_user", None)
        uid = from_user.id if from_user else 0
        now = time.monotonic()
        prev = self.last.get(uid, 0.0)
        if now - prev < self.rate:
            answer = getattr(event, "answer", None)
            if callable(answer):
                return await answer("Слишком часто. Подождите немного.")
            bot = data.get("bot")
            if bot and from_user:
                return await bot.send_message(from_user.id, "Слишком часто. Подождите немного.")
            return
        self.last[uid] = now
        return await handler(event, data)
