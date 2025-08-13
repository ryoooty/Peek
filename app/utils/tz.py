from __future__ import annotations

from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def tz_keyboard(prefix: str) -> InlineKeyboardMarkup:
    """Return inline keyboard with common UTC offsets.

    Args:
        prefix: prefix for callback data (e.g. ``tzstart`` or ``tzprof``).
    """
    offsets = [-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
    kb = InlineKeyboardBuilder()
    for h in offsets:
        kb.button(text=f"UTC{h:+d}", callback_data=f"{prefix}:{h*60}")
    kb.adjust(3)
    return kb.as_markup()
