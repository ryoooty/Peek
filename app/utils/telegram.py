from aiogram.exceptions import TelegramBadRequest

async def safe_edit_text(message, text: str, **kwargs):
    """Edit message text ignoring 'message is not modified' errors."""
    try:
        return await message.edit_text(text, **kwargs)
    except TelegramBadRequest as e:
        if "message is not modified" in e.message.lower():
            return None
        raise
