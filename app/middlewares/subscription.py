from __future__ import annotations

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from app.config import settings


class SubscriptionGateMiddleware(BaseMiddleware):
    """Проверяет подписку на канал.

    Пропускает только команды ``/start`` и callback ``gate:check``
    (а также действия админов). Бот должен быть админом канала.
    """

    async def __call__(self, handler, event: TelegramObject, data):
        channel_id = settings.sub_channel_id
        if not channel_id:
            return await handler(event, data)

        user_id = None
        is_start = False
        is_gate_check = False

        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
            cmd = (event.text or "").split()[0].lower()
            is_start = cmd == "/start"
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id if event.from_user else None
            is_gate_check = event.data == "gate:check"

        if not user_id:
            return await handler(event, data)

        if user_id in settings.admin_ids or is_start or is_gate_check:
            return await handler(event, data)

        # Проверка подписки
        try:
            member = await data["bot"].get_chat_member(chat_id=channel_id, user_id=user_id)
            status = getattr(member, "status", "left")
            ok = status in ("member", "administrator", "creator")
        except Exception:
            ok = True  # если нет прав видеть участников — пропускаем, чтобы не ломать UX

        if ok:
            return await handler(event, data)

        # Показать гейт
        url = None
        if settings.sub_channel_username:
            url = f"https://t.me/{settings.sub_channel_username.lstrip('@')}"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📣 Открыть канал", url=url or "https://t.me")],
            [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="gate:check")],
        ])
        if isinstance(event, Message):
            await event.answer("Подпишитесь на канал, чтобы продолжить.", reply_markup=kb)
        elif isinstance(event, CallbackQuery):
            await event.message.edit_text("Подпишитесь на канал, чтобы продолжить.", reply_markup=kb)
            await event.answer()
        return
