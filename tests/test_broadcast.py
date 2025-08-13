import sys
import types
import asyncio
import pytest

# provide minimal settings to avoid heavy dependencies
config_mod = types.ModuleType("app.config")
config_mod.settings = types.SimpleNamespace(admin_ids=[])
sys.modules.setdefault("app.config", config_mod)

from app.handlers import broadcast


class DummyQuery:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class DummyBot:
    def __init__(self, fail_ids=None):
        self.fail_ids = set(fail_ids or [])
        self.sent_messages = []
        self.sent_photos = []

    async def send_message(self, uid, text):
        if uid in self.fail_ids:
            raise Exception("fail")
        self.sent_messages.append((uid, text))

    async def send_photo(self, uid, photo, caption):
        if uid in self.fail_ids:
            raise Exception("fail")
        self.sent_photos.append((uid, photo, caption))


class DummyMessage:
    def __init__(self, bot):
        self.bot = bot
        self.answers = []

    async def answer(self, text):
        self.answers.append(text)


def test_do_broadcast_counts_success_and_error(monkeypatch):
    rows = [{"tg_id": "1"}, {"tg_id": "2"}, {"tg_id": "3"}]
    monkeypatch.setattr(broadcast.storage, "_q", lambda *a, **k: DummyQuery(rows))

    sent = []
    errors = []
    monkeypatch.setattr(broadcast.storage, "log_broadcast_sent", lambda uid: sent.append(uid))
    monkeypatch.setattr(
        broadcast.storage,
        "log_broadcast_error",
        lambda uid, note: errors.append(uid),
    )

    bot = DummyBot(fail_ids={2})
    msg = DummyMessage(bot)

    async def no_sleep(*args, **kwargs):
        pass

    monkeypatch.setattr(broadcast.asyncio, "sleep", no_sleep)

    asyncio.run(broadcast._do_broadcast(msg, text="hi", photo=None, audience="all"))

    assert sent == [1, 3]
    assert errors == [2]
    assert msg.answers == ["Рассылка завершена. Успешно: 2, ошибок: 1"]


def test_do_broadcast_with_photo(monkeypatch):
    rows = [{"tg_id": "1"}]
    monkeypatch.setattr(broadcast.storage, "_q", lambda *a, **k: DummyQuery(rows))

    bot = DummyBot()
    msg = DummyMessage(bot)

    async def no_sleep(*args, **kwargs):
        pass

    monkeypatch.setattr(broadcast.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(broadcast.storage, "log_broadcast_sent", lambda uid: None)
    monkeypatch.setattr(broadcast.storage, "log_broadcast_error", lambda uid, note: None)

    asyncio.run(broadcast._do_broadcast(msg, text="hello", photo="pid", audience="all"))

    assert bot.sent_photos == [(1, "pid", "hello")]
    assert msg.answers == ["Рассылка завершена. Успешно: 1, ошибок: 0"]
