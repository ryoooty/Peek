# app/mw/maintenance.py
from __future__ import annotations

from typing import Any, Callable, Awaitable, Optional, Iterable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, Update

from app.config import settings


def _is_admin(user_id: Optional[int]) -> bool:
    try:
        if user_id is None:
            return False
        return int(user_id) in {int(x) for x in (settings.admin_ids or [])}
    except Exception:
        return False


class MaintenanceMiddleware(BaseMiddleware):
    """
    В режиме техработ:
      - пропускаем все слэш-команды (/start, /help, /balance, ...);
      - пропускаем всё от админов;
      - гасим остальное.
    Для не-Message апдейтов (callback и пр.) аккуратно отвечаем alert'ом.
    """

    async def __call__(
        self,
        handler: Callable[[Update, dict[str, Any]], Awaitable[Any]],
        event: Update,  # фактический тип — конкретный объект апдейта (Message, CallbackQuery, ...)
        data: dict[str, Any],
    ) -> Any:
        # Если техработ нет — пропускаем всё
        if not settings.maintenance_mode:
            return await handler(event, data)

        # Message: пропускаем команды и админов
        if isinstance(event, Message):
            uid = event.from_user.id if event.from_user else None
            if _is_admin(uid):
                return await handler(event, data)
            text = event.text or event.caption or ""
            if isinstance(text, str) and text.startswith("/"):
                # это слэш-команда — пропускаем
                return await handler(event, data)
            # гасим прочие сообщения
            try:
                await event.answer("🛠 Сейчас идут техработы. Попробуйте позже.")
            except Exception:
                pass
            return

        # CallbackQuery: пропускаем админов, остальных гасим
        if isinstance(event, CallbackQuery):
            uid = event.from_user.id if event.from_user else None
            if _is_admin(uid):
                return await handler(event, data)
            try:
                await event.answer("🛠 Техработы. Попробуйте позже.", show_alert=True)
            except Exception:
                pass
            return

        # Любые другие типы апдейтов — пропустим только админов
        try:
            uid = getattr(getattr(event, "from_user", None), "id", None)
        except Exception:
            uid = None
        if _is_admin(uid):
            return await handler(event, data)
        # Иначе — тихо гасим
        return
