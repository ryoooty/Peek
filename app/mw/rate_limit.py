from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Callable, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

logger = logging.getLogger(__name__)


class RateLimitLLM(BaseMiddleware):
    """Queue incoming messages and process them sequentially."""

    def __init__(self, rate_seconds: int = 3):
        self.rate = max(0, int(rate_seconds))
        self._queues: dict[int, asyncio.Queue] = {}
        self._pending: asyncio.Queue[int] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None

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
        uid = getattr(from_user, "id", 0)

        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._worker())

        queue = self._queues.setdefault(uid, asyncio.Queue())
        await queue.put((handler, event, data))
        if queue.qsize() == 1:
            await self._pending.put(uid)
        return

    async def shutdown(self) -> None:
        """Cancel worker task and clear all queues."""
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
        self._queues.clear()
        self._pending = asyncio.Queue()

    async def _worker(self) -> None:
        while True:
            uid = await self._pending.get()
            queue = self._queues.get(uid)
            if queue is None:
                continue
            handler, event, data = await queue.get()
            try:
                await handler(event, data)
            except Exception:
                logging.exception("RateLimit handler failed")

            if not queue.empty():
                await self._pending.put(uid)
            if self.rate:
                await asyncio.sleep(self.rate)
