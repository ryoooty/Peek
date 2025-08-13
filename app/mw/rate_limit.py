from __future__ import annotations

import time
from typing import Any, Dict, Callable, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import Message

class RateLimitLLM(BaseMiddleware):
    """Простой RL: не троттлим команды (/...), только обычные сообщения."""
    def __init__(self, rate_seconds: int = 3):
        self.rate = max(0, int(rate_seconds))
        self.last: dict[int, float] = {}

    async def __call__(self, handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]], event: Message, data: Dict[str, Any]) -> Any:
        if not self.rate:
            return await handler(event, data)
        if event.text and event.text.startswith("/"):
            return await handler(event, data)  # команды не троттлим
        uid = event.from_user.id if event.from_user else 0
        now = time.monotonic()
        prev = self.last.get(uid, 0.0)
        if now - prev < self.rate:
            return await event.answer("Слишком часто. Подождите немного.")
        self.last[uid] = now
        return await handler(event, data)
