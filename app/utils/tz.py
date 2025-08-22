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


def parse_tz_offset(data: str) -> int:
    """Parse timezone offset from callback data.

    The data is expected in the format ``prefix:minutes`` where ``minutes`` is an
    integer number of minutes.  This helper is shared by handlers to avoid
    duplicating the parsing logic.

    :param data: Callback payload (e.g. ``"tz:180"``)
    :returns: Offset in minutes.
    :raises ValueError: If the payload does not contain a valid integer offset.
    """

    try:
        return int(data.split(":", 1)[1])
    except Exception as exc:  # pragma: no cover - clarity over micro-coverage
        raise ValueError("Invalid timezone offset") from exc

