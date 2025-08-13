from __future__ import annotations

from typing import Any, Dict, Callable, Awaitable, Optional

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import settings

CHECK_CB = "gate:check_sub"

def _gate_kb() -> Any:
    kb = InlineKeyboardBuilder()
    if settings.sub_channel_id:
        kb.button(text="Открыть канал", url=f"https://t.me/c/{str(settings.sub_channel_id).lstrip('-100')}")
    kb.button(text="✅ Проверить подписку", callback_data=CHECK_CB)
    kb.adjust(1)
    return kb.as_markup()

class ChannelSubscribeGate(BaseMiddleware):
    async def __call__(self, handler: Callable, event: Message, data: Dict[str, Any]) -> Any:  # type: ignore[override]
        if not settings.sub_channel_id:
            return await handler(event, data)
        if event.text and event.text.startswith("/"):
            cmd = event.text.split()[0].lower()
            if cmd in ("/start", "/help"):
                return await handler(event, data)
            if cmd == "/reload" and event.from_user and event.from_user.id in settings.admin_ids:
                return await handler(event, data)
        try:
            member = await data["bot"].get_chat_member(settings.sub_channel_id, event.from_user.id)  # type: ignore[arg-type]
            status = getattr(member, "status", "left")
            if status in ("left", "kicked"):
                return await event.answer("Подпишитесь на канал, чтобы пользоваться ботом.", reply_markup=_gate_kb())
        except Exception:
            pass
        return await handler(event, data)

class ChannelSubscribeGateCallback(BaseMiddleware):
    async def __call__(self, handler: Callable, event: CallbackQuery, data: Dict[str, Any]) -> Any:  # type: ignore[override]
        if not settings.sub_channel_id:
            return await handler(event, data)
        if event.data == CHECK_CB:
            return await handler(event, data)
        try:
            member = await data["bot"].get_chat_member(settings.sub_channel_id, event.from_user.id)  # type: ignore[arg-type]
            status = getattr(member, "status", "left")
            if status in ("left", "kicked"):
                await event.answer("Подпишитесь на канал, чтобы пользоваться ботом.", show_alert=True)
                return
        except Exception:
            pass
        return await handler(event, data)
