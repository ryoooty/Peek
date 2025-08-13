import asyncio
from types import SimpleNamespace
import time

from aiogram.types import Message
from app.mw.ban import BanMiddleware
from app.mw.rate_limit import RateLimitLLM
from app import storage


class DummyHandler:
    def __init__(self):
        self.called = False
    async def __call__(self, event, data):
        self.called = True
        return 'ok'


def test_ban_middleware_blocks_banned_user(tmp_path):
    async def run():
        storage.init(tmp_path / 'db.sqlite')
        storage.ensure_user(1, 'x')
        storage.set_user_field(1, 'banned', 1)
        msg = Message(from_user=SimpleNamespace(id=1))
        handler = DummyHandler()
        mw = BanMiddleware()
        await mw(handler, msg, {})
        assert handler.called is False
        assert msg.answers == ['Доступ ограничен.']
    asyncio.run(run())


def test_rate_limit_blocks_fast_messages(monkeypatch):
    async def run():
        rl = RateLimitLLM(rate_seconds=3)
        msg = Message(from_user=SimpleNamespace(id=2), text='hi')
        handler = DummyHandler()

        t = [10.0]
        monkeypatch.setattr(time, 'monotonic', lambda: t[0])
        await rl(handler, msg, {})
        assert handler.called

        handler.called = False
        t[0] = 11.0
        await rl(handler, msg, {})
        assert handler.called is False
        assert msg.answers[-1] == 'Слишком часто. Подождите немного.'

        handler.called = False
        cmd_msg = Message(from_user=SimpleNamespace(id=2), text='/start')
        t[0] = 11.5
        await rl(handler, cmd_msg, {})
        assert handler.called
    asyncio.run(run())
