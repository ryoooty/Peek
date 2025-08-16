from __future__ import annotations
import asyncio
import logging
from contextlib import asynccontextmanager
from aiogram import Bot

logger = logging.getLogger(__name__)

class TypingPacer:
    """
    Держит action 'typing' активным, пока идёт генерация.
    Полезно как в RP, так и в чат-режиме (между сегментами).
    """
    def __init__(self, bot: Bot, chat_id: int, interval: float = 4.5):
        # у Telegram действие «печатает…» живёт ~5с — пингуем чуть раньше
        self.bot = bot
        self.chat_id = chat_id
        self.interval = max(1.0, float(interval))
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def _pump(self):
        try:
            # первый «typing» — сразу, чтобы индикатор появился мгновенно
            await self.bot.send_chat_action(self.chat_id, "typing")
            while not self._stop.is_set():
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
                except asyncio.TimeoutError:
                    # обновляем индикатор
                    await self.bot.send_chat_action(self.chat_id, "typing")
        except asyncio.CancelledError:
            raise
        except Exception:
            # не падаем из-за сетевых мелочей
            logger.exception("Typing pump failed for chat %s", self.chat_id)

    def start(self):
        if not self._task:
            self._stop.clear()
            self._task = asyncio.create_task(self._pump())

    async def stop(self):
        if self._task:
            self._stop.set()
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Typing pacer stop failed for chat %s", self.chat_id)
            self._task = None

@asynccontextmanager
async def typing(bot: Bot, chat_id: int, interval: float = 4.5):
    """
    Контекст-менеджер:
        async with typing(bot, chat_id):
            ... долгая работа/стриминг ...
    """
    pacer = TypingPacer(bot, chat_id, interval=interval)
    pacer.start()
    try:
        yield pacer
    finally:
        await pacer.stop()
