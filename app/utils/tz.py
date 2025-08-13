from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def tz_keyboard() -> InlineKeyboardMarkup:
    keyboard = []
    row = []
    for offset in range(-12, 15):
        sign = "+" if offset >= 0 else "-"
        text = f"UTC{sign}{abs(offset):02d}"
        data = f"tz:{offset * 60}"
        row.append(InlineKeyboardButton(text=text, callback_data=data))
        if len(row) == 4:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
