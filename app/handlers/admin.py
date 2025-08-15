
from __future__ import annotations

import time
from pathlib import Path

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest
from aiogram.types.input_file import FSInputFile  # если будете где-то отправлять локальные файлы

from app.config import BASE_DIR, settings
from app import storage

router = Router(name="admin")


async def _require_admin(msg: Message) -> bool:
    uid = msg.from_user.id if msg.from_user else None
    if uid in settings.admin_ids:
        return True
    await msg.answer("Доступ запрещён")
    return False


MEDIA_DIR = Path(BASE_DIR) / "media" / "characters"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)


@router.message(Command("char_add"))
async def cmd_char_add(msg: Message):
    if not await _require_admin(msg):
        return

    parts = (msg.text or "").split(maxsplit=1)
    if len(parts) < 2:
        return await msg.answer(
            "Использование: /char_add <name>|<slug>|<fandom>|<описание>"
        )

    args = [p.strip() for p in parts[1].split("|")]
    while len(args) < 4:
        args.append("")
    name, slug, fandom, info_short = args[:4]

    char_id = storage.ensure_character(
        name,
        slug=slug or None,
        fandom=fandom or None,
        info_short=info_short or None,
    )
    await msg.answer(f"Персонаж создан: id={char_id}")


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

    if not storage.get_character(char_id):
        return await msg.answer("Персонаж не найден. Сначала создайте его через /char_add")

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


@router.message(Command("stats"))
async def cmd_stats(msg: Message):
    if not await _require_admin(msg):
        return
    days = storage.usage_by_day()
    weeks = storage.usage_by_week()
    top_chars = storage.top_characters()
    act_users = storage.active_users()
    lines = ["<b>Статистика</b>"]

    if days:
        lines.append("\n<b>Usage по дням</b>")
        for r in days:
            lines.append(f"{r['day']}: {r['in_tokens']}/{r['out_tokens']}")

    if weeks:
        lines.append("\n<b>Usage по неделям</b>")
        for r in weeks:
            lines.append(f"{r['week']}: {r['in_tokens']}/{r['out_tokens']}")

    if top_chars:
        lines.append("\n<b>Топ персонажей</b>")
        for r in top_chars:
            lines.append(f"{r['name']}: {r['cnt']}")

    if act_users:
        lines.append("\n<b>Активные пользователи</b>")
        for r in act_users:
            uname = r.get('username') or str(r['user_id'])
            lines.append(f"{uname}: {r['cnt']}")

    await msg.answer("\n".join(lines))

