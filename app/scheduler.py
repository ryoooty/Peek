# app/scheduler.py
from __future__ import annotations

import datetime as dt
import random
from typing import Optional, Dict, List

from aiogram import Bot
from app import storage, runtime
from app.config import settings


# APScheduler — опционально (без SQLAlchemyJobStore, чтобы не требовать SQLAlchemy)
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore
    from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore  # type: ignore
except Exception:
    AsyncIOScheduler = None  # type: ignore
    SQLAlchemyJobStore = None  # type: ignore

"""
ЛОГИКА (без «окон»):
— По завершении ответа ИИ планируем «проверку тишины» через 10 минут.
— Если тишина подтверждена, генерим N случайных таймингов на 24 часа вперёд (N = pro_per_day, дефолт 2).
— Тайминги живут как date‑jobs в APScheduler (in‑memory, без персиста).
— В момент тайминга:
   * берём АКТУАЛЬНЫЙ «последний чат» пользователя (если последний персонаж поменялся — шлём уже ему);
   * если была активность <5 минут назад — переносим на (now..+24h);
   * уважаем min_gap (дефолт 10 минут) от last_proactive_at;
   * отправляем через domain proactive_nudge; успешные попытки считаем на стороне domain/storage.
— «Потерянные» тайминги (бот был офлайн) не всплывут автоматически, но при ближайшей «тишине» сгенерим новый суточный план.
"""

# ---------------- Globals ----------------

_scheduler: Optional["AsyncIOScheduler"] = None
_bot: Optional[Bot] = None

# Для контроля: хранить ID поставленных джобов (чтобы знать, есть ли план у юзера)
_user_jobs: Dict[int, List[str]] = {}  # user_id -> [job_id,...]


# ---------------- Public API ----------------


def init(bot: Bot) -> None:
    """
    Запуск планировщика и периодических тиков.
    Без SQLAlchemyJobStore — ничего ставить/устанавливать не требуется.
    """
    global _scheduler, _bot
    _bot = bot
    if AsyncIOScheduler is None:
        # APScheduler не установлен — тихо деградируем
        return

    _scheduler = AsyncIOScheduler(timezone=dt.timezone.utc)
    _scheduler.start()
    runtime.set_scheduler(_scheduler)

    # Ежеминутный тик на случай подвисших/забытых пользователей:

    # Если у юзера включён Live и нет будущих джоб — создадим суточный план.
    _add_job("proactive:tick", "interval", minutes=1, func=_tick_fill_plans)
    _add_job("bonus:daily", "cron", hour=0, minute=5, func=_daily_bonus)
    _add_job("subs:expire", "cron", hour=0, minute=10, func=_subs_expire)


def shutdown() -> None:
    if _scheduler:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            pass


def schedule_silence_check(user_id: int, chat_id: int, delay_sec: int = 600) -> None:
    """
    Вызывается из чата: поставить «проверку тишины» через delay_sec (дефолт 10 минут).
    """
    if not _scheduler:
        return

    # удалить предыдущие джобы тишины этого пользователя
    try:
        for j in list(_scheduler.get_jobs()):  # type: ignore
            if j.id and j.id.startswith(f"silence:{user_id}:"):
                try:
                    _scheduler.remove_job(j.id)
                except Exception:
                    pass
    except Exception:
        pass

    run_at = dt.datetime.utcnow() + dt.timedelta(seconds=int(delay_sec))
    jid = f"silence:{user_id}:{int(run_at.timestamp())}"
    _add_job(jid, "date", run_date=run_at, func=_on_silence, args=(user_id, chat_id))
    _user_jobs[user_id] = [jid]

def rebuild_user_jobs(user_id: int) -> None:
    """Пересобрать или очистить суточный план Live для пользователя.

    Удаляет все существующие джобы пользователя (nudge и silence) и,
    при активном режиме Live — создаёт новый дневной план.
    """
    if not _scheduler:
        return

    # удалить старые джобы пользователя
    try:
        for j in list(_scheduler.get_jobs()):  # type: ignore
            if not j.id:
                continue
            if j.id.startswith(f"nudge:{user_id}:") or j.id.startswith(
                f"silence:{user_id}:"
            ):
                try:
                    _scheduler.remove_job(j.id)
                except Exception:
                    pass
    except Exception:
        pass
    _user_jobs.pop(user_id, None)

    # пересоздать план, только если Live включён
    u = storage.get_user(user_id) or {}
    if int(u.get("proactive_enabled") or 0) == 1:
        _plan_daily(user_id)


# ---------------- Internal helpers/jobs ----------------

def _add_job(job_id: str, trigger: str, **kw) -> None:
    if not _scheduler:
        return
    try:
        _scheduler.add_job(id=job_id, trigger=trigger, replace_existing=False, **kw)  # type: ignore
    except Exception:
        # не критично
        pass


async def _daily_bonus() -> None:
    uids = storage.daily_bonus_free_users()
    if not _bot or not uids:
        return
    amount = int(settings.subs.nightly_toki_bonus.get("free", 0))
    for uid in uids:
        try:
            await _bot.send_message(uid, f"💰 Ежедневный бонус: +{amount} токов")
        except Exception:
            pass


async def _subs_expire() -> None:
    uids = storage.expire_subscriptions()
    if not _bot or not uids:
        return
    for uid in uids:
        try:
            await _bot.send_message(uid, "❗️ Срок действия подписки истёк")
        except Exception:
            pass


def _parse_hhmm(s: str) -> tuple[int, int]:
    return int(s[:2]), int(s[3:5])


def _today_utc(h: int, m: int, *, day_shift: int = 0) -> dt.datetime:
    now = dt.datetime.now(dt.timezone.utc)
    return now.replace(hour=h, minute=m, second=0, microsecond=0) + dt.timedelta(days=day_shift)


def schedule_window_jobs_for_user(user_id: int) -> None:
    if not _scheduler:
        return
    u = storage.get_user(user_id) or {}
    if int(u.get("proactive_enabled") or 0) != 1:
        return
    win = str(u.get("pro_window_utc") or "06:00-18:00")
    s, e = win.split("-")
    sh, sm = _parse_hhmm(s)
    eh, em = _parse_hhmm(e)
    for shift in (0, 1):
        start_dt = _today_utc(sh, sm, day_shift=shift)
        end_dt = _today_utc(eh, em, day_shift=shift)
        try:
            _scheduler.add_job(
                _on_window_start,
                trigger="date",
                run_date=start_dt,
                id=f"winstart:{user_id}:{shift}",
                args=(user_id,),
                replace_existing=True,
            )
            _scheduler.add_job(
                _on_window_end,
                trigger="date",
                run_date=end_dt,
                id=f"winend:{user_id}:{shift}",
                args=(user_id,),
                replace_existing=True,
            )
        except Exception:
            continue


def rebuild_all_window_jobs() -> None:
    if not _scheduler:
        return
    for uid in storage.select_proactive_candidates():
        schedule_window_jobs_for_user(uid)


def _on_window_start(user_id: int) -> None:
    _plan_daily(user_id)
    schedule_window_jobs_for_user(user_id)


def _on_window_end(user_id: int) -> None:
    if not _scheduler:
        return
    for j in list(_scheduler.get_jobs()):  # type: ignore
        if j.id and (j.id.startswith(f"nudge:{user_id}:") or j.id.startswith(f"silence:{user_id}:")):
            try:
                _scheduler.remove_job(j.id)
            except Exception:
                continue
    schedule_window_jobs_for_user(user_id)


def _now_ts() -> int:
    return int(dt.datetime.utcnow().timestamp())


def _get_user_settings(user_id: int) -> tuple[int, int, int]:
    """
    Возвращает (min_delay_sec, max_delay_sec, min_gap_sec).
    """
    u = storage.get_user(user_id) or {}
    min_delay_sec = int(u.get("pro_min_delay_min") or 60) * 60  # дефолт 60 мин
    max_delay_sec = int(u.get("pro_max_delay_min") or 720) * 60  # дефолт 720 мин
    min_gap_sec = int(u.get("pro_min_gap_min") or 10) * 60  # дефолт 10 мин
    return min_delay_sec, max_delay_sec, min_gap_sec


def _get_last_chat_id(user_id: int) -> Optional[int]:
    last = storage.get_last_chat(user_id)
    try:
        return int(last["id"]) if last else None
    except Exception:
        return None


def _last_message_recent(chat_id: int, secs: int) -> bool:
    """
    Есть ли сообщение (от кого угодно) за последние `secs` секунд.
    """
    ts = storage.last_message_ts(chat_id)
    if not ts:
        return False
    return (dt.datetime.now(dt.timezone.utc) - ts).total_seconds() < secs


def _last_proactive_ts(user_id: int) -> Optional[int]:
    try:
        rows = storage.query(
            "SELECT strftime('%s', COALESCE(last_proactive_at, 0)) AS ts FROM users WHERE tg_id=?",
            (user_id,),
        )
        r = rows[0] if rows else None
        return int(r["ts"]) if r and r["ts"] else None
    except Exception:
        return None


def _rand_between(start_ts: int, end_ts: int) -> int:
    return random.randint(start_ts, end_ts)



def _get_delay_range_sec(user_id: int) -> tuple[int, int]:
    """Пара (min,max) задержки в секундах для пользователя."""
    return storage.get_delay_range(user_id)


def _schedule_next(user_id: int, delay_sec: Optional[int] = None) -> None:
    """Поставить следующий нудж через случайный интервал и сохранить план."""
    if not _scheduler:
        return
    u = storage.get_user(user_id) or {}
    if int(u.get("proactive_enabled") or 0) != 1:
        return
    last_chat = _get_last_chat_id(user_id)
    if not last_chat:
        return
    if delay_sec is None:
        mn, mx = _get_delay_range_sec(user_id)
        delay_sec = _rand_between(int(mn), int(mx))
    when_ts = _now_ts() + int(delay_sec)
    jid = f"nudge:{user_id}:{when_ts}"
    _add_job(jid, "date", run_date=dt.datetime.utcfromtimestamp(when_ts), func=_on_nudge_due, args=(user_id,))
    _user_jobs[user_id] = [jid]
    try:
        storage.delete_future_plan(user_id)
        storage.insert_plan(user_id, last_chat, when_ts)
    except Exception:
        pass



async def _tick_fill_plans():
    """
    Раз в минуту: если у юзера Live включён и будущих джоб нет — создадим новый тайминг.
    (Мягкий автозапуск, чтобы план не «забывался».)
    """
    if not _scheduler:
        return
    now = _now_ts()
    for uid in storage.select_proactive_candidates():
        # есть ли хотя бы одна наша джоба для пользователя в будущем?
        has_future = False
        for j in _scheduler.get_jobs():  # type: ignore
            if j.id and (j.id.startswith(f"nudge:{uid}:") or j.id.startswith(f"silence:{uid}:")):
                try:
                    if j.next_run_time and int(j.next_run_time.timestamp()) > now:
                        has_future = True
                        break
                except Exception:
                    continue

        if not has_future:
            _schedule_next(uid)



async def _on_silence(user_id: int, chat_id: int):
    """
    Через 10 минут после завершения ответа ИИ:
    — подтверждаем тишину (последние ~9 минут),
    — если у пользователя нет из будущих нудж‑джоб — ставим новый дневной план.
    """
    if not _scheduler:
        return
    # подтверждение тишины
    if _last_message_recent(chat_id, 9 * 60):
        return

    # Уже есть будущее?
    now = _now_ts()
    for j in _scheduler.get_jobs():  # type: ignore
        if j.id and j.id.startswith(f"nudge:{user_id}:"):
            try:
                if j.next_run_time and int(j.next_run_time.timestamp()) > now:
                    return  # план уже есть
            except Exception:
                continue

    # создаём новый тайминг
    _schedule_next(user_id)


async def _on_nudge_due(user_id: int):
    """
    Срабатывание конкретного тайминга: «попробовать отправить».
    Всегда шлём в АКТУАЛЬНЫЙ last_chat пользователя.
    При невозможности — переносим на случайное время в (now..+24h).
    """
    last_chat = _get_last_chat_id(user_id)
    if not last_chat:
        # нет чатов — перенести
        _schedule_next(user_id)
        return

    now = _now_ts()
    # если была активность <5 минут назад — перенос
    if _last_message_recent(last_chat, 5 * 60):
        _schedule_next(user_id)
        return


    # min_gap
    _, _, min_gap = _get_user_settings(user_id)
    last_sent = _last_proactive_ts(user_id)
    if last_sent and (now - last_sent) < min_gap:
        wait = last_sent + min_gap + _rand_between(30, 300) - now
        _schedule_next(user_id, delay_sec=wait)
        return

    # попытка отправки (через доменную функцию)
    ok = await _try_send_nudge(user_id, last_chat)
    # назначаем следующий тайминг независимо от результата
    _schedule_next(user_id)
    if ok:
        return



async def _try_send_nudge(user_id: int, chat_id: int) -> bool:
    """
    Вызов доменной функции проактива. Путь подбираем гибко:
    1) app.domain.proactive.proactive_nudge
    2) app.proactive.proactive_nudge
    """
    fn = None
    try:
        from app.domain.proactive import proactive_nudge as fn  # type: ignore
    except Exception:
        try:
            from app.proactive import proactive_nudge as fn  # type: ignore
        except Exception:
            fn = None

    if not fn or not _bot:
        return False

    try:
        text = await fn(bot=_bot, user_id=user_id, chat_id=chat_id)
        return bool(text)
    except Exception:
        return False
