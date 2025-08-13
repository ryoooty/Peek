from __future__ import annotations

import time
from pathlib import Path

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import Message

from app import storage
from app.config import BASE_DIR, reload_settings, settings
from app.scheduler import rebuild_user_jobs

router = Router(name="admin")


async def _require_admin(msg: Message) -> bool:
    """Return True if message author is allowed to use admin commands."""
    return msg.from_user.id in settings.admin_ids


MEDIA_DIR = Path(BASE_DIR) / "media" / "characters"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)


@router.message(Command("reload"))
async def cmd_reload(msg: Message):
    if not await _require_admin(msg):
        return
    reload_settings()
    try:
        rows = storage._q("SELECT tg_id FROM users").fetchall()
        for r in rows:
            rebuild_user_jobs(int(r["tg_id"]))
    except Exception:
        pass
    await msg.answer("Конфигурация перезагружена ✅")


@router.message(Command("maintenance"))
async def cmd_maintenance(msg: Message):
    if not await _require_admin(msg):
        return
    parts = (msg.text or "").split()
    if len(parts) == 1:
        await msg.answer(
            f"Maintenance: {'ON' if settings.maintenance_mode else 'OFF'}\nИспользуйте: /maintenance on|off"
        )
        return
    arg = parts[1].lower()
    if arg in ("on", "off"):
        settings.maintenance_mode = arg == "on"
        await msg.answer(
            f"Maintenance переключён: {'ON' if settings.maintenance_mode else 'OFF'}"
        )
    else:
        await msg.answer("Используйте: /maintenance on|off")


@router.message(Command("char_photo"))
async def cmd_char_photo(msg: Message):
    if not await _require_admin(msg):
        return
    parts = (msg.text or "").split()
    if len(parts) < 2 and not (msg.caption or "").startswith("/char_photo"):
        return await msg.answer(
            "Использование: отправьте фото с подписью: <code>/char_photo &lt;id&gt;</code>"
        )

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
        return await msg.answer(
            "Неверный id. Пример: <code>/char_photo 123</code>"
        )

    file_id = None
    if msg.photo:
        file_id = msg.photo[-1].file_id
    elif msg.reply_to_message and msg.reply_to_message.photo:
        file_id = msg.reply_to_message.photo[-1].file_id
    if not file_id:
        return await msg.answer(
            "Пришлите фото с подписью команды или ответом на фото.\nПример: <code>/char_photo 123</code>"
        )

    try:
        fl = await msg.bot.get_file(file_id)
        ext = Path(fl.file_path or "photo.jpg").suffix or ".jpg"
        save_name = f"{char_id}_{int(time.time())}{ext}"
        save_path = MEDIA_DIR / save_name
        await msg.bot.download(file=fl.file_id, destination=save_path)
    except TelegramBadRequest:
        try:
            fl = await msg.bot.get_file(file_id)
            ext = Path(fl.file_path or "photo.jpg").suffix or ".jpg"
            save_name = f"{char_id}_{int(time.time())}{ext}"
            save_path = MEDIA_DIR / save_name
            await msg.bot.download(file=fl, destination=save_path)
        except Exception as e:
            return await msg.answer(f"Не удалось скачать фото: <code>{e}</code>")

    storage.set_character_photo_path(char_id, str(save_path.as_posix()))

    await msg.answer(
        "Фото сохранено ✅\nПуть: <code>{}</code>".format(save_path.as_posix())
    )

