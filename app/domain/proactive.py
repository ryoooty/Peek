from __future__ import annotations

import datetime as dt
from typing import Optional

from aiogram import Bot

from app import storage
from app.config import settings
from app.character import LIVE_STYLE
from app.providers.deepseek_openai import chat as provider_chat


async def can_send_now(user_id: int) -> tuple[bool, str]:
    u = storage.get_user(user_id) or {}
    if not int(u.get("proactive_enabled") or 0):
        return False, "disabled"
    per_day = int(u.get("pro_per_day") or 1)
    min_gap_min = int(u.get("pro_min_gap_min") or 120)
    count_today = storage.proactive_count_today(user_id)
    if count_today >= per_day:
        return False, "limit"
    # проверка на минимальный интервал
    last = u.get("last_proactive_at")
    if last:
        try:
            last_dt = dt.datetime.fromisoformat(last)
        except Exception:
            last_dt = None
        if last_dt:
            if (dt.datetime.utcnow() - last_dt).total_seconds() < min_gap_min * 60:
                return False, "gap"
    return True, "ok"


async def proactive_nudge(*, bot: Bot, user_id: int, chat_id: int) -> Optional[str]:
    """
    Сгенерировать и отправить короткий нудж в чат с учётом ограничений.
    Возвращает текст нуджа или None, если отправка не требуется.
    """
    ok, reason = await can_send_now(user_id)
    if not ok:
        return None

    chat = storage.get_chat(chat_id) or {}
    if not chat or int(chat.get("user_id") or 0) != user_id:
        return None

    # Контекст: последние 8 сообщений + системная подсказка Live
    msgs = storage.list_messages(chat_id, limit=16)
    context = []
    for m in msgs[-8:]:
        who = "Пользователь" if m["is_user"] else (chat.get("char_name") or "Персонаж")
        context.append(f"{who}: {m['content']}")

    sys = (
        LIVE_STYLE
        + "\nНапиши дружелюбное короткое сообщение-продолжение диалога (1–3 предложения), "
        "без извинений и служебных фраз, без смайлов, если их не было. "
        "Сохраняй характер персонажа. Избегай повторов предыдущих фраз."
    )
    model = (storage.get_user(user_id) or {}).get("default_model") or settings.default_model
    try:
        r = await provider_chat(
            model=model,
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": "\n".join(context) or "Начинай дружелюбно беседу."},
            ],
            temperature=0.7,
            max_tokens=180,
            timeout_s=settings.limits.request_timeout_seconds,
        )
    except Exception:
        storage.log_proactive(user_id, chat_id, int(chat["char_id"]), "error")
        return None
    text = (r.text or "").strip()
    if not text:
        return None

    # Биллинг: первые 2 нуджа бесплатны
    u = storage.get_user(user_id) or {}
    free_used = int(u.get("pro_free_used") or 0)
    kind = "free" if free_used < 2 else "paid"
    if kind == "free":
        storage.set_user_field(user_id, "pro_free_used", free_used + 1)
    else:
        # стоимость задаётся в конфиге; списываем независимо от usage (фикс за проактив)
        cost = int(settings.limits.proactive_cost_tokens or 0)
        if cost > 0:
            storage.spend_tokens(user_id, cost)

    # Сохраняем и отправляем
    storage.add_message(chat_id, is_user=False, content=text, usage_in=int(r.usage_in or 0), usage_out=int(r.usage_out or 0))
    storage.log_proactive(user_id, chat_id, int(chat["char_id"]), kind)
    try:
        await bot.send_message(chat_id=user_id, text=text)
    except Exception:
        # fallback: игнорируем ошибки доставки
        pass
    return text
