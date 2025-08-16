from __future__ import annotations

import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app import runtime, storage
from app.config import reload_settings, settings

from app.scheduler import rebuild_user_jobs

logger = logging.getLogger(__name__)

router = Router(name="system")


@router.message(Command("reload"))
async def cmd_reload(msg: Message):
    if msg.from_user.id not in settings.admin_ids:
        return
    reload_settings()
    # Пересоберём джобы для всех пользователей
    from app import storage
    try:
        rows = storage.query("SELECT tg_id FROM users")
        for r in rows:
            rebuild_user_jobs(int(r["tg_id"]))
    except Exception:
        logger.exception("Failed to rebuild user jobs on reload")
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


@router.message(Command("diag"))
async def cmd_diag(msg: Message):
    if msg.from_user.id not in settings.admin_ids:
        return
    scheduler = runtime.get_scheduler()
    job_ids: list[str] = []
    if scheduler:
        try:
            job_ids = [j.id or "" for j in scheduler.get_jobs()]
        except Exception:
            logger.exception("Failed to collect scheduler jobs")
    gate_state = "ON" if settings.sub_channel_id else "OFF"
    err_counts = runtime.get_error_counts()
    err_text = ", ".join(f"{k}={v}" for k, v in err_counts.items()) or "—"
    text = (
        f"Config v{settings.config_version}\n"
        f"Jobs ({len(job_ids)}): {', '.join(job_ids) if job_ids else '—'}\n"
        f"Sub gate: {gate_state}\n"
        f"Errors: {err_text}"


    )
    await msg.answer(text)


@router.message(Command("health"))
async def cmd_health(msg: Message):
    if msg.from_user.id not in settings.admin_ids:
        return
    tables = ["users", "characters", "chats", "messages"]
    try:
        for t in tables:
            storage.query(f"SELECT 1 FROM {t} LIMIT 1")
    except Exception as e:
        runtime.incr_error("db")
        await msg.answer(f"DB error: {e}")
        return
    await msg.answer("OK")

