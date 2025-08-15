import sys
import asyncio
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

import aiogram


class _StubBot:
    async def send_message(self, *args, **kwargs):
        pass


if not hasattr(aiogram, "Bot"):
    aiogram.Bot = _StubBot

from app import storage, scheduler


class DummyBot:
    async def send_message(self, *args, **kwargs):
        raise AssertionError("send_message should not be called")


def test_provider_error_does_not_break_scheduler(tmp_path, monkeypatch):
    storage.init(tmp_path / "db.sqlite")
    user_id = 1
    storage.ensure_user(user_id, "u")
    char_id = storage.ensure_character("Char")
    chat_id = storage.create_chat(user_id, char_id)

    scheduler._bot = DummyBot()

    async def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.domain.proactive.provider_chat", boom)
    monkeypatch.setattr(scheduler, "_get_last_chat_id", lambda uid: chat_id)
    monkeypatch.setattr(scheduler, "_last_message_recent", lambda cid, secs: False)
    monkeypatch.setattr(scheduler, "_get_user_settings", lambda uid: (0, 0, 0))
    monkeypatch.setattr(scheduler, "_last_proactive_ts", lambda uid: None)

    scheduled = {}

    def fake_schedule_next(uid, delay_sec=None):
        scheduled["called"] = True

    monkeypatch.setattr(scheduler, "_schedule_next", fake_schedule_next)

    asyncio.run(scheduler._on_nudge_due(user_id))

    assert scheduled.get("called")

    scheduler._bot = None
