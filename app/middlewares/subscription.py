from __future__ import annotations

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from app.config import settings


class SubscriptionGateMiddleware(BaseMiddleware):
    """
    Проверяет подписку на канал для всех действий, кроме слэш-команд и админов.
    Бот должен быть админом канала.
    """

    async def __call__(self, handler, event: TelegramObject, data):
        channel_id = settings.sub_channel_id
        if not channel_id:
            return await handler(event, data)

        user_id = None
        is_command = False
        chat_id = None

        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
            chat_id = event.chat.id
            is_command = (event.text or "").startswith("/")
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id if event.from_user else None
            chat_id = event.message.chat.id if event.message else None
            is_command = False

        if not user_id:
            return await handler(event, data)

        if user_id in settings.admin_ids:
            return await handler(event, data)

        if is_command:
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
