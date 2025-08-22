import sys
import types
from types import SimpleNamespace

# stub storage and tz to avoid heavy dependencies
storage_stub = types.ModuleType("app.storage")
storage_stub.get_user = lambda user_id: {}
stored = {}

def _set(user_id, field, value):
    stored["user_id"] = user_id
    stored["field"] = field
    stored["value"] = value

storage_stub.set_user_field = _set
sys.modules["app.storage"] = storage_stub

tz_stub = types.ModuleType("app.utils.tz")
tz_stub.tz_keyboard = lambda *_, **__: "KB"
tz_stub.parse_tz_offset = lambda s: 180 if s.strip().replace(" ", "") in {"+3", "+03", "+03:00"} else None
sys.modules["app.utils.tz"] = tz_stub

from app.middlewares.timezone import TimezoneMiddleware
import asyncio


def test_timezone_prompt():
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


def test_timezone_manual_input():
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
    assert stored["value"] == 180
    assert not called
