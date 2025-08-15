import sys


if not hasattr(sys.modules.get("aiogram"), "Bot"):
    class _DummyBot:
        def __init__(self, *args, **kwargs):
            pass

    sys.modules.setdefault("aiogram", type("x", (), {})())
    sys.modules["aiogram"].Bot = _DummyBot

from app import scheduler, storage


class DummyScheduler:
    def __init__(self):
        self.calls = []

    def add_job(self, *args, **kwargs):
        self.calls.append((args, kwargs))

    def get_jobs(self):
        return []


def test_schedule_window_jobs_invalid_window(monkeypatch):
    dummy = DummyScheduler()
    scheduler._scheduler = dummy

    def fake_get_user(uid):
        return {"proactive_enabled": 1, "pro_window_utc": "invalid"}

    monkeypatch.setattr(storage, "get_user", fake_get_user)

    try:
        scheduler.schedule_window_jobs_for_user(1)
    finally:
        scheduler._scheduler = None

    assert len(dummy.calls) == 4
