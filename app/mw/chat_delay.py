from __future__ import annotations

import logging
import time
from collections import OrderedDict
from typing import Any, Dict, Callable, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app import storage

logger = logging.getLogger(__name__)


class ChatDelayMiddleware(BaseMiddleware):
    """Block messages arriving faster than chat's min_delay_ms."""

    def __init__(self, maxsize: int = 1024) -> None:
        # Mapping of chat_id -> timestamp of last processed message
        self._last: "OrderedDict[int, float]" = OrderedDict()
        self._maxsize = maxsize

    def _cleanup(self, now: float, delay: float) -> None:
        """Remove stale entries and limit mapping size.

        Entries older than ``delay * 2`` are pruned to keep the mapping small.
        Additionally the mapping is capped at ``self._maxsize`` items using
        least-recently-used eviction.
        """

        cutoff = now - delay * 2
        stale = [cid for cid, ts in self._last.items() if ts < cutoff]
        for cid in stale:
            del self._last[cid]

        while len(self._last) > self._maxsize:
            # Remove the oldest item
            self._last.popitem(last=False)

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
        self._cleanup(now, delay)
        prev = self._last.get(chat_id, 0.0)
        if now - prev < delay:
            answer = getattr(event, "answer", None)
            if callable(answer):
                try:
                    await answer("Подождите немного перед следующим сообщением.")
                except Exception:
                    logger.exception(
                        "Failed to warn user %s about chat delay", from_user.id
                    )
            else:
                bot = data.get("bot")
                if bot and from_user:
                    try:
                        await bot.send_message(
                            from_user.id, "Подождите немного перед следующим сообщением."
                        )
                    except Exception:
                        logger.exception(
                            "Failed to send delay message to user %s", from_user.id
                        )
            return
        self._last[chat_id] = now
        self._last.move_to_end(chat_id)
        return await handler(event, data)
