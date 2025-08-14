from __future__ import annotations

from aiogram import Router, F
from aiogram.types import CallbackQuery

from app.config import settings
from app.utils.telegram import safe_edit_text

router = Router(name="gate")


@router.callback_query(F.data == "gate:check")
async def cb_gate_check(call: CallbackQuery):
    if not settings.sub_channel_id:
        return await call.answer("Проверка не настроена", show_alert=True)
    try:
        m = await call.message.bot.get_chat_member(chat_id=settings.sub_channel_id, user_id=call.from_user.id)
        status = getattr(m, "status", "left")
        if status in ("member", "administrator", "creator"):
            await call.answer("Спасибо! Подписка подтверждена.")
            await safe_edit_text(call.message, "Готово. Вы можете продолжать.")
        else:
            await call.answer("Ещё не подписаны.", show_alert=True)
    except Exception:
        await call.answer("Не удалось проверить подписку", show_alert=True)
