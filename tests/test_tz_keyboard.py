import sys
import importlib
from types import SimpleNamespace

import pytest

# Replace aiogram button/markup with simple containers for testing
types_mod = sys.modules.setdefault("aiogram.types", SimpleNamespace())

class Button:
    def __init__(self, text: str, callback_data: str):
        self.text = text
        self.callback_data = callback_data


class Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


types_mod.InlineKeyboardButton = Button
types_mod.InlineKeyboardMarkup = Markup

# Ensure we load the real tz module (other tests may stub it)
sys.modules.pop("app.utils.tz", None)
tz_module = importlib.import_module("app.utils.tz")
tz_keyboard = tz_module.tz_keyboard


def _flatten(kb):
    return [btn for row in kb.inline_keyboard for btn in row]


def test_tz_keyboard_hour_steps_with_skip():
    kb = tz_keyboard()
    buttons = _flatten(kb)
    data_to_text = {btn.callback_data: btn.text for btn in buttons}

    # Skip button present
    assert "tz:skip" in data_to_text
    assert data_to_text["tz:skip"] == "Пропустить"

    values = sorted(
        int(k.split(":", 1)[1]) for k in data_to_text.keys() if k != "tz:skip"
    )

    assert values[0] == -12 * 60
    assert values[-1] == 12 * 60
    assert len(values) == 25

    diffs = {b - a for a, b in zip(values, values[1:])}
    assert diffs == {60}

    # Check extremes formatted correctly
    assert data_to_text["tz:-720"] == "UTC-12"
    assert data_to_text["tz:720"] == "UTC+12"
