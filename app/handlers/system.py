from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import reload_settings, settings
from app.scheduler import rebuild_user_jobs

router = Router(name="system")


@router.message(Command("reload"))
async def cmd_reload(msg: Message):
    if msg.from_user.id not in settings.admin_ids:
        return
    reload_settings()
    # Пересоберём джобы для всех пользователей
    from app import storage
    try:
        rows = storage._q("SELECT tg_id FROM users").fetchall()
        for r in rows:
            rebuild_user_jobs(int(r["tg_id"]))
    except Exception:
        pass
    await msg.answer("Конфигурация перезагружена ✅")


@router.message(Command("maintenance"))
async def cmd_maintenance(msg: Message):
    if msg.from_user.id not in settings.admin_ids:
        return
    parts = (msg.text or "").split()
    if len(parts) == 1:
        await msg.answer(f"Maintenance: {'ON' if settings.maintenance_mode else 'OFF'}\nИспользуйте: /maintenance on|off")
        return
    arg = parts[1].lower()
    if arg in ("on", "off"):
        settings.maintenance_mode = (arg == "on")
        await msg.answer(f"Maintenance переключён: {'ON' if settings.maintenance_mode else 'OFF'}")
    else:
        await msg.answer("Используйте: /maintenance on|off")
