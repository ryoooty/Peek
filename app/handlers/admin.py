from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app import storage
from app.config import settings

router = Router(name="admin")


@router.message(Command("char_add"))
async def cmd_char_add(msg: Message):
    if msg.from_user.id not in settings.admin_ids:
        return
    # /char_add <name> [fandom] [info_short...]
    parts = (msg.text or "").split(maxsplit=2)
    if len(parts) < 2:
        return await msg.answer("Использование: /char_add <name> [fandom] [info_short]")
    name = parts[1]
    fandom = None
    info = None
    if len(parts) >= 3:
        tmp = parts[2].split(maxsplit=1)
        fandom = tmp[0]
        info = tmp[1] if len(tmp) > 1 else None
    cid = storage.ensure_character(name, fandom=fandom, info_short=info)
    await msg.answer(
        f"Персонаж «{name}» создан (id={cid}).\n"
        f"Пришлите фото с подписью: /char_photo {cid}"
    )


@router.message(Command("char_photo"))
async def cmd_char_photo(msg: Message):
    if msg.from_user.id not in settings.admin_ids:
        return
    parts = (msg.text or "").split()
    if len(parts) < 2:
        return await msg.answer("Использование: отправьте фото с подписью: /char_photo <char_id>")
    try:
        char_id = int(parts[1])
    except Exception:
        return await msg.answer("Неверный id.")
    file_id = None
    if msg.photo:
        file_id = msg.photo[-1].file_id
    elif msg.reply_to_message and msg.reply_to_message.photo:
        file_id = msg.reply_to_message.photo[-1].file_id
    if not file_id:
        return await msg.answer("Пришлите фото с этой командой в подписи или ответом на фото.")
    storage.set_character_photo(char_id, file_id)
    await msg.answer("Фото обновлено ✅")
