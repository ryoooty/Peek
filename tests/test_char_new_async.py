import asyncio
import time
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import aiogram.types as tg_types

tg_types.InputMediaPhoto = SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
config_module = types.ModuleType("app.config")
config_module.BASE_DIR = ROOT
config_module.settings = SimpleNamespace()
sys.modules["app.config"] = config_module

from app import storage
from app.handlers.characters import cb_char_new

del sys.modules["app.config"]


def test_cb_char_new_nonblocking(monkeypatch):
    next_id = {"val": 1}

    def create_chat(user_id, char_id):
        cid = next_id["val"]
        next_id["val"] += 1
        return cid

    monkeypatch.setattr(storage, "create_chat", create_chat)

    opened = []

    async def open_chat_inline_stub(call, chat_id):
        opened.append(chat_id)
        await asyncio.sleep(0.1)

    chats_stub = types.ModuleType("app.handlers.chats")
    chats_stub.open_chat_inline = open_chat_inline_stub
    monkeypatch.setitem(sys.modules, "app.handlers.chats", chats_stub)

    class Call:
        def __init__(self, char_id):
            self.data = f"char:new:{char_id}"
            self.from_user = SimpleNamespace(id=123)
            self.answers = []

        async def answer(self, text, show_alert=False):
            self.answers.append(text)

    async def run():
        c1, c2 = Call(1), Call(2)
        t0 = time.monotonic()
        await cb_char_new(c1)
        t1 = time.monotonic()
        await cb_char_new(c2)
        t2 = time.monotonic()
        await asyncio.sleep(0.11)
        return c1, c2, opened, t1 - t0, t2 - t1

    call1, call2, opened_ids, d1, d2 = asyncio.run(run())

    assert d1 < 0.05 and d2 < 0.05
    assert call1.answers == ["Создаю чат…"]
    assert call2.answers == ["Создаю чат…"]
    assert opened_ids == [1, 2]
