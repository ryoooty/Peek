from __future__ import annotations

import asyncio


from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import settings
from app import storage

router = Router(name="broadcast")

BATCH_SIZE = 30
PAUSE_BETWEEN_BATCHES = 1.0
DELAY_BETWEEN_SEND = 0.05


def _audience_query(audience: str) -> str:
    if audience == "all":
        return "SELECT tg_id FROM users WHERE banned=0"
    return "SELECT tg_id FROM users WHERE banned=0 AND subscription='free'"


async def _do_broadcast(msg: Message, *, text: str, photo: str | None, audience: str) -> None:
    rows = storage._q(_audience_query(audience)).fetchall()
    user_ids = [int(r["tg_id"]) for r in rows]
    sent = 0
    failed = 0
    for idx, uid in enumerate(user_ids, start=1):
        try:
            if photo:
                await msg.bot.send_photo(uid, photo=photo, caption=text)
            else:
                await msg.bot.send_message(uid, text)
            storage.log_broadcast_sent(uid)
            sent += 1
        except Exception as e:  # noqa: BLE001
            storage.log_broadcast_error(uid, str(e))
            failed += 1
        if idx % BATCH_SIZE == 0:
            await asyncio.sleep(PAUSE_BETWEEN_BATCHES)
        else:
            await asyncio.sleep(DELAY_BETWEEN_SEND)
    await msg.answer(f"Рассылка завершена. Успешно: {sent}, ошибок: {failed}")



@router.message(Command("broadcast"))
async def cmd_broadcast(msg: Message) -> None:
    if msg.from_user.id not in settings.admin_ids:
        return
    parts = (msg.text or "").split(maxsplit=2)
    if len(parts) < 3 or parts[1] not in {"all", "free"}:
        await msg.answer("Использование: /broadcast <all|free> <текст>")
        return
    audience = parts[1]
    text = parts[2]
    await _do_broadcast(msg, text=text, photo=None, audience=audience)


@router.message(Command("broadcast_photo"))
async def cmd_broadcast_photo(msg: Message) -> None:
    if msg.from_user.id not in settings.admin_ids:
        return
    parts = (msg.caption or "").split(maxsplit=2)
    if not msg.photo or len(parts) < 3 or parts[1] not in {"all", "free"}:
        await msg.answer(
            "Пришлите фото с подписью: /broadcast_photo <all|free> <текст>"
        )
        return
    audience = parts[1]
    text = parts[2]
    file_id = msg.photo[-1].file_id
    await _do_broadcast(msg, text=text, photo=file_id, audience=audience)

