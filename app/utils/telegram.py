from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

async def safe_edit_text(message, text: str, callback: CallbackQuery | None = None, **kwargs):
    """Edit message text ignoring common non-critical errors."""
    try:
        return await message.edit_text(text, **kwargs)
    except TelegramBadRequest as e:
        msg = e.message.lower()
        if "message is not modified" in msg:
            return None
        if (
            "message can't be edited" in msg
            or "there is no text in the message to edit" in msg
        ):
            if callback:
                try:
                    await callback.answer(
                        "Сообщение слишком старое. Telegram не позволяет его редактировать.",
                        show_alert=False,
                    )
                except Exception:
                    pass
            return None
        raise
