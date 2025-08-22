import re

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def parse_tz_offset(data: str | None) -> int | None:
    """Parse timezone offset from user text or callback payload.

    Supports human-friendly formats like ``+3``, ``-03`` or ``4:30`` as well as
    callback payloads in the form ``"tz:180"``. Returns offset in minutes or
    ``None`` if the value cannot be parsed. For callback payloads an invalid
    integer after the colon raises ``ValueError``.
    """
    if data is None:
        return None
    text = data.strip()
    if not text:
        return None
    if re.match(r"^[A-Za-z]+:", text):
        try:
            return int(text.split(":", 1)[1])
        except Exception as exc:  # pragma: no cover - clarity over micro-coverage
            raise ValueError("Invalid timezone offset") from exc
    m = re.fullmatch(r"([+-])?\s*(\d{1,2})(?::(\d{2}))?", text)
    if not m:
        return None
    sign, hours_s, minutes_s = m.groups()
    hours = int(hours_s)
    minutes = int(minutes_s) if minutes_s else 0
    if hours > 12 or minutes not in (0, 30):
        return None
    total = hours * 60 + minutes
    if sign == "-":
        total = -total
    return total


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
