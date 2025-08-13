# app/scheduler.py
from __future__ import annotations

import datetime as dt
import random
from typing import Optional, Dict, List

from aiogram import Bot
from app import storage
from app.config import settings

# APScheduler — опционально (без SQLAlchemyJobStore, чтобы не требовать SQLAlchemy)
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore
except Exception:
    AsyncIOScheduler = None  # type: ignore

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

    # Ежеминутный тик на случай подвисших/забытых пользователей:
    # Если у юзера включён Live и нет будущих джоб — создадим суточный план.
    _add_job("proactive:tick", "interval", minutes=1, func=_tick_fill_plans)
    _add_job("bonus:daily", "cron", hour=0, minute=5, func=_daily_bonus)


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
    run_at = dt.datetime.utcnow() + dt.timedelta(seconds=int(delay_sec))
    jid = f"silence:{user_id}:{int(run_at.timestamp())}"
    _add_job(jid, "date", run_date=run_at, func=_on_silence, args=(user_id, chat_id))


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
    if not _bot:
        return
    amount = int(settings.nightly_toki_bonus.get("free") or 0)
    for uid in uids:
        try:
            await _bot.send_message(uid, f"💰 Ежедневный бонус: +{amount} токов")
        except Exception:
            pass


def _now_ts() -> int:
    return int(dt.datetime.utcnow().timestamp())


def _get_user_settings(user_id: int) -> tuple[int, int]:
    """
    Возвращает (per_day, min_gap_sec) с дефолтами (2; 600).
    """
    u = storage.get_user(user_id) or {}
    per_day = int(u.get("pro_per_day") or 2)            # дефолт 2
    min_gap_sec = int(u.get("pro_min_gap_min") or 10) * 60  # дефолт 10 мин
    return per_day, min_gap_sec


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
        r = storage._q(
            "SELECT strftime('%s', COALESCE(last_proactive_at, 0)) AS ts FROM users WHERE tg_id=?",
            (user_id,),
        ).fetchone()
        return int(r["ts"]) if r and r["ts"] else None
    except Exception:
        return None


def _rand_between(start_ts: int, end_ts: int) -> int:
    return random.randint(start_ts, end_ts)


def _gen_random_slots(n: int, *, start_ts: int, end_ts: int, min_gap_sec: int, last_sent_ts: Optional[int]) -> List[int]:
    """
    Генерация N случайных таймингов в [start, end], соблюдая min_gap и отступ от last_sent_ts.
    """
    if n <= 0 or end_ts - start_ts < min_gap_sec:
        return []
    out: List[int] = []
    attempts = 0
    while len(out) < n and attempts < 500:
        attempts += 1
        t = _rand_between(start_ts, end_ts)
        if any(abs(t - x) < min_gap_sec for x in out):
            continue
        if last_sent_ts and abs(t - last_sent_ts) < min_gap_sec:
            continue
        out.append(t)
    return sorted(out)


async def _tick_fill_plans():
    """
    Раз в минуту: если у юзера Live включён и будущих джоб нет — создадим суточный план.
    (Мягкий автозапуск, чтобы планы не «забывались».)
    """
    if not _scheduler:
        return
    rows = storage._q("SELECT tg_id, proactive_enabled FROM users").fetchall()
    now = _now_ts()
    for r in rows:
        uid = int(r["tg_id"])
        if int(r["proactive_enabled"] or 0) != 1:
            continue
        # есть ли хотя бы одна наша джоба для пользователя в будущем?
        has_future = False
        for j in _scheduler.get_jobs():  # type: ignore
            if j.id and (j.id.startswith(f"nudge:{uid}:") or j.id.startswith(f"silence:{uid}:")):
                # если дата запуска в будущем — ок
                try:
                    if j.next_run_time and int(j.next_run_time.timestamp()) > now:
                        has_future = True
                        break
                except Exception:
                    continue
        if not has_future:
            # сгенерить суточный план от «сейчас»
            _plan_daily(uid)


def _plan_daily(user_id: int) -> None:
    """
    Сгенерировать N таймингов на 24 часа вперёд и поставить джобы отправки.
    """
    if not _scheduler:
        return
    last_chat = _get_last_chat_id(user_id)
    if not last_chat:
        return
    per_day, min_gap = _get_user_settings(user_id)
    now = _now_ts()
    horizon = now + 24 * 3600
    last_sent = _last_proactive_ts(user_id)
    slots = _gen_random_slots(per_day, start_ts=now, end_ts=horizon, min_gap_sec=min_gap, last_sent_ts=last_sent)

    ids = []
    for t in slots:
        jid = f"nudge:{user_id}:{t}"
        _add_job(jid, "date", run_date=dt.datetime.utcfromtimestamp(t), func=_on_nudge_due, args=(user_id,))
        ids.append(jid)
    _user_jobs[user_id] = ids


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

    # создаём новый суточный план
    _plan_daily(user_id)


async def _on_nudge_due(user_id: int):
    """
    Срабатывание конкретного тайминга: «попробовать отправить».
    Всегда шлём в АКТУАЛЬНЫЙ last_chat пользователя.
    При невозможности — переносим на случайное время в (now..+24h).
    """
    last_chat = _get_last_chat_id(user_id)
    if not last_chat:
        # нет чатов — перенести
        _reschedule_in(user_id, seconds=_rand_between(60, 24 * 3600))
        return

    now = _now_ts()
    # если была активность <5 минут назад — перенос
    if _last_message_recent(last_chat, 5 * 60):
        _reschedule_in(user_id, seconds=_rand_between(60, 24 * 3600))
        return

    # min_gap
    _, min_gap = _get_user_settings(user_id)
    last_sent = _last_proactive_ts(user_id)
    if last_sent and (now - last_sent) < min_gap:
        _reschedule_at(user_id, when_ts=last_sent + min_gap + _rand_between(30, 300))
        return

    # попытка отправки (через доменную функцию)
    ok = await _try_send_nudge(user_id, last_chat)
    if ok:
        # успех — ничего не делаем (domain уже записал логи/usage)
        return
    # неудача — перенести
    _reschedule_in(user_id, seconds=_rand_between(60, 24 * 3600))


def _reschedule_in(user_id: int, *, seconds: int) -> None:
    _reschedule_at(user_id, when_ts=_now_ts() + int(seconds))


def _reschedule_at(user_id: int, *, when_ts: int) -> None:
    if not _scheduler:
        return
    jid = f"nudge:{user_id}:{when_ts}"
    _add_job(jid, "date", run_date=dt.datetime.utcfromtimestamp(when_ts), func=_on_nudge_due, args=(user_id,))
    _user_jobs.setdefault(user_id, []).append(jid)


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
