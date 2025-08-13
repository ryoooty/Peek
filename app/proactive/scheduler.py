from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from aiogram import Bot
from apscheduler.triggers.date import DateTrigger

from app import storage
from app.runtime import get_scheduler
from app.domain.proactive import proactive_nudge

def _parse_hhmm(s: str) -> tuple[int, int]:
    return int(s[:2]), int(s[3:5])

def _today_utc(h: int, m: int, *, day_shift: int = 0) -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=h, minute=m, second=0, microsecond=0) + timedelta(days=day_shift)

def schedule_window_jobs_for_user(user_id: int) -> None:
    """
    Поставить джобы «старт/конец» на сегодня и завтра (UTC).
    """
    sch = get_scheduler()
    if not sch:
        return
    u = storage.get_user(user_id) or {}
    if not (u.get("proactive_enabled") or 0):
        return
    win = str(u.get("pro_window_utc") or "06:00-18:00")
    s, e = win.split("-")
    sh, sm = _parse_hhmm(s)
    eh, em = _parse_hhmm(e)

    for shift in (0, 1):
        start_dt = _today_utc(sh, sm, day_shift=shift)
        end_dt = _today_utc(eh, em, day_shift=shift)
        sch.add_job(_job_run_user, trigger=DateTrigger(run_date=start_dt), id=f"pro_start:{user_id}:{shift}", kwargs={"user_id": user_id, "reason": "window_start"}, replace_existing=True)
        sch.add_job(_job_run_user, trigger=DateTrigger(run_date=end_dt), id=f"pro_end:{user_id}:{shift}", kwargs={"user_id": user_id, "reason": "window_end"}, replace_existing=True)

def rebuild_all_window_jobs() -> None:
    sch = get_scheduler()
    if not sch:
        return
    try:
        for uid in storage.select_proactive_candidates():
            schedule_window_jobs_for_user(uid)
    except Exception:
        pass

def schedule_silence_job(user_id: int, *, seconds: int = 600) -> None:
    """
    Отложенное задание «через 10 минут тишины». Старое задание перезаписывается.
    """
    sch = get_scheduler()
    if not sch:
        return
    run_at = datetime.now(timezone.utc) + timedelta(seconds=int(seconds))
    sch.add_job(_job_run_user, trigger=DateTrigger(run_date=run_at), id=f"pro_idle:{user_id}", kwargs={"user_id": user_id, "reason": "idle_10m"}, replace_existing=True)

async def _job_run_user(user_id: int, reason: str) -> None:
    """
    Обёртка, которую вызывает планировщик (бот берём из job context через kwargs).
    """
    sch = get_scheduler()
    if not sch:
        return
    bot: Optional[Bot] = getattr(sch, "_bot", None)  # см. bot.py — мы присваиваем _bot
    if not bot:
        return
    try:
        await proactive_nudge(bot, user_id, reason=reason)
    except Exception:
        # не роняем планировщик
        return
