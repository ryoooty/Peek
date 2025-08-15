from __future__ import annotations

import time
from typing import Any, Dict, Callable, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app import storage


class ChatDelayMiddleware(BaseMiddleware):
    """Block messages arriving faster than chat's min_delay_ms."""

    def __init__(self) -> None:
        self._last: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        text = getattr(event, "text", None)
        if not text or text.startswith("/"):
            return await handler(event, data)
        from_user = data.get("event_from_user") or getattr(event, "from_user", None)
        user_id = getattr(from_user, "id", None)
        if not user_id:
            return await handler(event, data)
        last = storage.get_last_chat(user_id)
        if not last:
            return await handler(event, data)
        chat_id = int(last["id"])
        chat = storage.get_chat(chat_id) or {}
        delay_ms = int(chat.get("min_delay_ms") or 0)
        if delay_ms <= 0:
            return await handler(event, data)
        delay = delay_ms / 1000.0
        now = time.monotonic()
        prev = self._last.get(chat_id, 0.0)
        if now - prev < delay:
            answer = getattr(event, "answer", None)
            if callable(answer):
                try:
                    await answer("Подождите немного перед следующим сообщением.")
                except Exception:
                    pass
            else:
                bot = data.get("bot")
                if bot and from_user:
                    try:
                        await bot.send_message(from_user.id, "Подождите немного перед следующим сообщением.")
                    except Exception:
                        pass
            return
        self._last[chat_id] = now
        return await handler(event, data)
