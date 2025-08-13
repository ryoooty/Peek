import types
import sys
from pathlib import Path

import asyncio
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from app import storage
from app.handlers.balance import cb_open_balance, cmd_balance


class DummyMessage:
    def __init__(self, user_id: int, username: str | None = None):
        self.from_user = types.SimpleNamespace(id=user_id, username=username)
        self.sent: list[str] = []

    async def answer(self, text: str):
        self.sent.append(text)


class DummyCall:
    def __init__(self, user_id: int):
        self.from_user = types.SimpleNamespace(id=user_id)
        self.message = DummyMessage(user_id)

    async def answer(self, *args, **kwargs):  # pragma: no cover - nothing to return
        pass


def test_cb_open_balance_sends_new_message(tmp_path):
    storage.init(tmp_path / "db.sqlite")
    storage.ensure_user(1, "test")
    call = DummyCall(1)
    asyncio.run(cb_open_balance(call))
    assert call.message.sent and "Баланс" in call.message.sent[0]


def test_cmd_balance_sends_new_message(tmp_path):
    storage.init(tmp_path / "db2.sqlite")
    storage.ensure_user(2, "test2")
    msg = DummyMessage(2)
    asyncio.run(cmd_balance(msg))
    assert msg.sent and "Баланс" in msg.sent[0]

