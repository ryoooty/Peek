from __future__ import annotations

import asyncio
import time
from typing import List

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import settings
from app import storage

router = Router(name="broadcast")

# how many messages to send before short pause
_STEP = 30
_PAUSE = 1


@router.message(Command("broadcast"))
async def cmd_broadcast(msg: Message) -> None:
    """Admin command to broadcast a text or photo message."""
    if msg.from_user.id not in settings.admin_ids:
        return

    src = msg.text or msg.caption or ""
    parts = src.split(maxsplit=2)
    if len(parts) < 3:
        await msg.answer("Использование: /broadcast all|free текст (или с фото)")
        return

    audience = parts[1].lower()
    content = parts[2]
    photo_id = msg.photo[-1].file_id if msg.photo else None

    if audience not in {"all", "free"}:
        await msg.answer("Укажите аудиторию: all или free")
        return

    if audience == "free":
        rows = storage._q(
            "SELECT tg_id FROM users WHERE banned=0 AND (subscription IS NULL OR subscription='free')"
        ).fetchall()
    else:
        rows = storage._q("SELECT tg_id FROM users WHERE banned=0").fetchall()

    user_ids: List[int] = [int(r["tg_id"]) for r in rows]
    total = len(user_ids)
    await msg.answer(f"Начинаю рассылку: {total} получателей")

    run_id = str(int(time.time()))
    ok, fail = 0, 0

    for idx, uid in enumerate(user_ids, start=1):
        try:
            if photo_id:
                await msg.bot.send_photo(uid, photo_id, caption=content)
            else:
                await msg.bot.send_message(uid, content)
            storage.log_broadcast(run_id, uid, "ok")
            ok += 1
        except Exception as e:  # pragma: no cover - network errors are possible
            storage.log_broadcast(run_id, uid, "fail", str(e))
            fail += 1
        if idx % _STEP == 0:
            await asyncio.sleep(_PAUSE)

    await msg.answer(f"Рассылка завершена. Успешно: {ok}, ошибок: {fail}.")
