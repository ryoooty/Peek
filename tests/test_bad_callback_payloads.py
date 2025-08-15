import asyncio
import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def _load_handlers():
    config_module = types.ModuleType("app.config")
    config_module.BASE_DIR = ROOT
    config_module.settings = SimpleNamespace()
    sys.modules["app.config"] = config_module

    scheduler_module = types.ModuleType("app.scheduler")
    scheduler_module.schedule_silence_check = lambda *args, **kwargs: None
    sys.modules["app.scheduler"] = scheduler_module

    chats = importlib.import_module("app.handlers.chats")
    characters = importlib.import_module("app.handlers.characters")
    cb_open_chat = chats.cb_open_chat
    cb_chats_page = chats.cb_chats_page
    cb_open_char = characters.cb_open_char

    for m in [
        "app.config",
        "app.scheduler",
        "app.handlers.chats",
        "app.handlers.characters",
        "app.domain.chats",
        "app.billing.pricing",
    ]:
        sys.modules.pop(m, None)

    return cb_open_chat, cb_chats_page, cb_open_char


class Call:
    def __init__(self, data):
        self.data = data
        self.from_user = SimpleNamespace(id=123)
        self.message = SimpleNamespace()
        self.answers = []

    async def answer(self, text, show_alert=False):
        self.answers.append((text, show_alert))


def test_bad_callback_payloads():
    cb_open_chat, cb_chats_page, cb_open_char = _load_handlers()

    async def run():
        cases = [
            (cb_open_chat, "chat:open:abc"),
            (cb_open_chat, "chat:open"),
            (cb_open_char, "char:open:xyz"),
            (cb_open_char, "char:open"),
            (cb_chats_page, "chats:page:foo"),
            (cb_chats_page, "chats:page"),
        ]
        results = []
        for handler, payload in cases:
            call = Call(payload)
            await handler(call)
            results.append(call)
        return results

    calls = asyncio.run(run())
    for c in calls:
        assert c.answers == [("Некорректные данные", True)]
