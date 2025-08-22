import re

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def parse_tz_offset(value: str | None) -> int | None:
    """Parse timezone offset.

    Handles both manual text input (``+3``, ``-03:30``) and callback payloads
    like ``"tz:180"``. For manual input returns ``None`` if the value is
    invalid. For callback payloads raises :class:`ValueError` when parsing
    fails.
    """

    if value is None:

        return None
    text = data.strip()
    if not text:
        return None

    if ":" in text and text.split(":", 1)[0].isalpha():
        try:
            return int(text.split(":", 1)[1])
        except Exception as exc:  # pragma: no cover
            raise ValueError("Invalid timezone offset") from exc

    m = re.fullmatch(r"([+-])?\s*(\d{1,2})(?:[:\s]*(\d{2}))?", text)
    if not m:
        return None


    m = re.fullmatch(r"([+-])?\s*(\d{1,2})(?:[:\s]*(\d{2}))?", text)


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

