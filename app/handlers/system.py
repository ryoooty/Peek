from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import config_version, reload_settings, settings
from app.runtime import get_error_counters, get_scheduler
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


@router.message(Command("diag"))
async def cmd_diag(msg: Message):
    if msg.from_user.id not in settings.admin_ids:
        return
    sched = get_scheduler()
    jobs = []
    if sched:
        try:
            jobs = sched.get_jobs()
        except Exception:
            jobs = []
    gate = "ON" if settings.sub_channel_id else "OFF"
    errors = get_error_counters()
    job_ids = ", ".join(j.id for j in jobs if getattr(j, "id", None)) or "none"
    text = (
        f"Config version: {config_version}\n"
        f"Jobs ({len(jobs)}): {job_ids}\n"
        f"Sub gate: {gate}\n"
        f"Errors: {errors}"
    )
    await msg.answer(text)


@router.message(Command("health"))
async def cmd_health(msg: Message):
    if msg.from_user.id not in settings.admin_ids:
        return
    from app import storage

    tables = ["users", "characters", "chats", "messages", "fav_chars", "proactive_plan", "proactive_log", "topups"]
    results = []
    for t in tables:
        try:
            storage._q(f"SELECT 1 FROM {t} LIMIT 1")
            results.append(f"{t}: ok")
        except Exception as e:
            results.append(f"{t}: {e}")
    try:
        qc = storage._q("PRAGMA quick_check").fetchone()
        results.append(f"quick_check: {qc[0] if qc else 'unknown'}")
    except Exception as e:
        results.append(f"quick_check: {e}")
    await msg.answer("Health:\n" + "\n".join(results))
