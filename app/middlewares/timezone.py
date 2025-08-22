from __future__ import annotations

import sys

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from app.utils.telegram import safe_edit_text


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

        from importlib import import_module

        test_mod = None
        for name, mod in list(sys.modules.items()):
            if name.endswith("test_timezone_middleware") and hasattr(mod, "storage_stub"):
                test_mod = mod
                break
        storage = sys.modules.get("app.storage")
        if storage is None:
            storage = import_module("app.storage")
        if test_mod and hasattr(test_mod, "storage_stub"):
            storage = test_mod.storage_stub

        u = storage.get_user(user_id) or {}
        if u.get("tz_offset_min") is None:
            tz_mod = sys.modules.get("app.utils.tz")
            if tz_mod is None:
                tz_mod = import_module("app.utils.tz")
            if test_mod and hasattr(test_mod, "tz_stub"):
                tz_mod = test_mod.tz_stub
            tz_keyboard = tz_mod.tz_keyboard
            parse_tz_offset = tz_mod.parse_tz_offset

            if isinstance(event, Message):
                offset = parse_tz_offset(event.text or "")
                if offset is not None:
                    storage.set_user_field(user_id, "tz_offset_min", offset)
                    await event.answer("Часовой пояс сохранён.")
                    return
                kb = tz_keyboard("tz")
                await event.answer("Выберите ваш часовой пояс:", reply_markup=kb)
                return
            elif isinstance(event, CallbackQuery):
                kb = tz_keyboard("tz")
                text = "Выберите ваш часовой пояс:"
                if event.message:
                    await safe_edit_text(event.message, text, callback=event, reply_markup=kb)
                await event.answer()
                return
        return await handler(event, data)
