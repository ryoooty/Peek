import importlib
import sys
import types
from types import SimpleNamespace
import asyncio


def _setup(monkeypatch, stored):
    import app.storage as storage

    def _set(user_id, field, value):
        stored["user_id"] = user_id
        stored["field"] = field
        stored["value"] = value

    monkeypatch.setattr(storage, "get_user", lambda uid: {})
    monkeypatch.setattr(storage, "set_user_field", _set)

    tz_stub = types.ModuleType("app.utils.tz")
    tz_stub.tz_keyboard = lambda *_, **__: "KB"
    tz_stub.parse_tz_offset = (
        lambda s: 180 if s.strip().replace(" ", "") in {"+3", "+03", "+03:00"} else None
    )
    monkeypatch.setitem(sys.modules, "app.utils.tz", tz_stub)

    monkeypatch.delitem(sys.modules, "app.middlewares.timezone", raising=False)
    return importlib.import_module("app.middlewares.timezone").TimezoneMiddleware


def test_timezone_prompt(monkeypatch):
    stored = {}
    TimezoneMiddleware = _setup(monkeypatch, stored)

    prompts = {}

    from aiogram.types import Message as AiogramMessage

    class Message(AiogramMessage):
        def __init__(self):
            self.from_user = SimpleNamespace(id=1)
            self.text = ""

        async def answer(self, text, reply_markup=None):
            prompts["text"] = text
            prompts["reply_markup"] = reply_markup

    message = Message()

    called = False

    async def handler(event, data):
        nonlocal called
        called = True

    async def run():
        mw = TimezoneMiddleware()
        await mw(handler, message, {})

    asyncio.run(run())

    assert prompts["text"] == "Выберите ваш часовой пояс:"
    assert prompts["reply_markup"] == "KB"
    assert not called


def test_timezone_manual_input(monkeypatch):
    stored = {}
    TimezoneMiddleware = _setup(monkeypatch, stored)

    prompts = {}

    from aiogram.types import Message as AiogramMessage

    class Message(AiogramMessage):
        def __init__(self):
            self.from_user = SimpleNamespace(id=1)
            self.text = "+3"

        async def answer(self, text, reply_markup=None):
            prompts["text"] = text

    message = Message()

    called = False

    async def handler(event, data):
        nonlocal called
        called = True

    async def run():
        mw = TimezoneMiddleware()
        await mw(handler, message, {})

    asyncio.run(run())

    assert prompts["text"] == "Часовой пояс сохранён."
    assert stored.get("value") == 180
    assert not called

