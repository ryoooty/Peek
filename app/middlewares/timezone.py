from __future__ import annotations

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from app import storage
from app.utils.tz import tz_keyboard


class TimezoneMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data):
        user_id = None
        is_start = False
        is_tz_cb = False
        is_gate_cb = False

        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
            is_start = (event.text or "").startswith("/start")
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id if event.from_user else None
            data_str = event.data or ""
            is_tz_cb = data_str.startswith("tz:")
            is_gate_cb = data_str.startswith("gate:")

        if not user_id or is_start or is_tz_cb or is_gate_cb:
            return await handler(event, data)

        u = storage.get_user(user_id) or {}
        if u.get("tz_offset_min") is None:
            kb = tz_keyboard()
            text = "Выберите ваш часовой пояс:"
            if isinstance(event, Message):
                await event.answer(text, reply_markup=kb)
            elif isinstance(event, CallbackQuery):
                if event.message:
                    await event.message.edit_text(text, reply_markup=kb)
                await event.answer()
            return
        return await handler(event, data)
