from __future__ import annotations

import re

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def parse_tz_offset(value: str | None) -> int | None:
    """Parse timezone offset string into minutes.

    Accepts formats like ``+3``, ``- 3``, ``-03`` or ``+03:00`` with optional
    spaces or colon separator. Hours must be in ``0..12`` and minutes can be
    only ``00`` or ``30``. Returns offset in minutes or ``None`` if input is
    invalid.
    """

    if not value:
        return None

    text = value.strip()
    if not text:
        return None

    m = re.fullmatch(r"([+-])?\s*(\d{1,2})(?:[:\s]*(\d{2}))?", text)
    if not m:
        return None

    sign, hour_s, minute_s = m.groups()
    hours = int(hour_s)
    minutes = int(minute_s) if minute_s else 0

    if hours > 12:
        return None
    if minutes not in (0, 30):
        return None

    offset = hours * 60 + minutes
    if sign == "-":
        offset = -offset
    return offset


def tz_keyboard(prefix: str = "tz") -> InlineKeyboardMarkup:
    keyboard = []
    row = []
    for offset in range(-12 * 60, 12 * 60 + 1, 60):
        abs_offset = abs(offset)
        hours = abs_offset // 60
        sign = "+" if offset >= 0 else "-"
        text = f"UTC{sign}{hours:02d}"
        data = f"{prefix}:{offset}"
        row.append(InlineKeyboardButton(text=text, callback_data=data))
        if len(row) == 4:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(text="Пропустить", callback_data=f"{prefix}:skip")])
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

