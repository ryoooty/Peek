# >>> admin.py
from __future__ import annotations

import time
from pathlib import Path

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.types.input_file import FSInputFile  # если будете где-то отправлять локальные файлы

from app import storage
from app.config import BASE_DIR, settings


router = Router(name="admin")


async def _require_admin(msg: Message) -> bool:
    if msg.from_user.id not in settings.admin_ids:
        await msg.answer("Нет доступа")
        return False
    return True

MEDIA_DIR = Path(BASE_DIR) / "media" / "characters"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

@router.message(Command("char_photo"))
async def cmd_char_photo(msg: Message):
    if not await _require_admin(msg):
        return
    parts = (msg.text or "").split()
    if len(parts) < 2 and not (msg.caption or "").startswith("/char_photo"):
        return await msg.answer(
            "Использование: отправьте фото с подписью: <code>/char_photo &lt;id&gt;</code>"
        )

    # id берём либо из текста, либо из подписи
    char_id = None
    for source in (msg.text or "", msg.caption or ""):
        ps = source.split()
        if len(ps) >= 2 and ps[0] == "/char_photo":
            try:
                char_id = int(ps[1])
                break
            except Exception:
                pass
    if not char_id:
        return await msg.answer("Неверный id. Пример: <code>/char_photo 123</code>")

    # достаём file_id из фото
    file_id = None
    if msg.photo:
        file_id = msg.photo[-1].file_id
    elif msg.reply_to_message and msg.reply_to_message.photo:
        file_id = msg.reply_to_message.photo[-1].file_id
    if not file_id:
        return await msg.answer(
            "Пришлите фото с подписью команды или ответом на фото.\nПример: <code>/char_photo 123</code>"
        )

    # cкачиваем фото в media/characters
    try:
        fl = await msg.bot.get_file(file_id)
        # Обычно Telegram даёт .jpg; на всякий случай определим расширение из пути
        ext = Path(fl.file_path or "photo.jpg").suffix or ".jpg"
        save_name = f"{char_id}_{int(time.time())}{ext}"
        save_path = MEDIA_DIR / save_name
        await msg.bot.download(file=fl.file_id, destination=save_path)
    except TelegramBadRequest:
        # fallback: если download по file_id не сработал — пробуем через file_path
        try:
            fl = await msg.bot.get_file(file_id)
            ext = Path(fl.file_path or "photo.jpg").suffix or ".jpg"
            save_name = f"{char_id}_{int(time.time())}{ext}"
            save_path = MEDIA_DIR / save_name
            await msg.bot.download(file=fl, destination=save_path)
        except Exception as e:
            return await msg.answer(f"Не удалось скачать фото: <code>{e}</code>")

    # сохраняем путь и file_id в БД
    storage.set_character_photo_path(char_id, str(save_path.as_posix()))
    storage.set_character_photo(char_id, file_id)

    await msg.answer(
        "Фото сохранено ✅\nПуть: <code>{}</code>".format(save_path.as_posix())
    )
