from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def tz_keyboard(prefix: str = "tz") -> InlineKeyboardMarkup:
    keyboard = []
    row = []
    for offset in range(-12 * 60, 14 * 60 + 1, 30):
        abs_offset = abs(offset)
        hours = abs_offset // 60
        minutes = abs_offset % 60
        sign = "+" if offset >= 0 else "-"
        text = f"UTC{sign}{hours:02d}:{minutes:02d}"
        data = f"{prefix}:{offset}"
        row.append(InlineKeyboardButton(text=text, callback_data=data))
        if len(row) == 4:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

