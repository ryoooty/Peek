import asyncio
import datetime as dt
import sys
import pytest

try:
    import pydantic
    import pydantic_settings
    import aiogram
    if not hasattr(aiogram, "Bot"):  # pragma: no cover
        class _StubBot:
            async def send_message(self, *args, **kwargs):
                pass

        aiogram.Bot = _StubBot
except ImportError:  # pragma: no cover - executed only without deps
    import types

    pydantic = types.ModuleType("pydantic")

    class _BaseModel:
        def __init__(self, *args, **kwargs):
            pass

    def _Field(*args, **kwargs):
        default = kwargs.get("default")
        if "default_factory" in kwargs:
            return kwargs["default_factory"]()
        return default

    pydantic.BaseModel = _BaseModel
    pydantic.Field = _Field
    sys.modules["pydantic"] = pydantic

    pydantic_settings = types.ModuleType("pydantic_settings")

    class _BaseSettings:
        def __init__(self, *args, **kwargs):
            pass

    def _SettingsConfigDict(**kwargs):
        return kwargs

    pydantic_settings.BaseSettings = _BaseSettings
    pydantic_settings.SettingsConfigDict = _SettingsConfigDict
    sys.modules["pydantic_settings"] = pydantic_settings

    aiogram = types.ModuleType("aiogram")

    class _StubBot:
        async def send_message(self, *args, **kwargs):
            pass

    aiogram.Bot = _StubBot
    sys.modules["aiogram"] = aiogram

from app import scheduler, storage


class DummyBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, uid, text):
        self.sent.append((uid, text))


def _fmt(ts: dt.datetime) -> str:
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def test_expired_subscription_downgrades_and_notifies(tmp_path):
    storage.init(tmp_path / "db.sqlite")
    storage.ensure_user(1, "u1")
    past = dt.datetime.utcnow() - dt.timedelta(days=1)
    storage.set_user_field(1, "subscription", "pro")
    storage.set_user_field(1, "sub_end", _fmt(past))

    bot = DummyBot()
    scheduler._bot = bot
    asyncio.run(scheduler._subs_expire())
    scheduler._bot = None

    u = storage.get_user(1)
    assert u["subscription"] == "free"
    assert bot.sent and bot.sent[0][0] == 1


def test_active_subscription_untouched(tmp_path):
    storage.init(tmp_path / "db2.sqlite")
    storage.ensure_user(2, "u2")
    future = dt.datetime.utcnow() + dt.timedelta(days=1)
    storage.set_user_field(2, "subscription", "pro")
    storage.set_user_field(2, "sub_end", _fmt(future))

    bot = DummyBot()
    scheduler._bot = bot
    asyncio.run(scheduler._subs_expire())
    scheduler._bot = None

    u = storage.get_user(2)
    assert u["subscription"] == "pro"
    assert not bot.sent


def test_expire_subscriptions_downgrades_direct(tmp_path):
    storage.init(tmp_path / "db3.sqlite")
    storage.ensure_user(3, "u3")
    past = dt.datetime.utcnow() - dt.timedelta(days=1)
    storage.set_user_field(3, "subscription", "pro")
    storage.set_user_field(3, "sub_end", _fmt(past))

    affected = storage.expire_subscriptions(col="sub_end")

    assert affected == [3]
    u = storage.get_user(3)
    assert u["subscription"] == "free"
    assert u["sub_end"] is None


def test_expire_subscriptions_rejects_invalid_column(tmp_path):
    storage.init(tmp_path / "db4.sqlite")
    storage.ensure_user(4, "u4")
    with pytest.raises(ValueError):
        storage.expire_subscriptions(col="sub_end; DROP TABLE users;--")

    # Table should remain intact
    storage.ensure_user(5, "u5")
    u = storage.get_user(5)
    assert u["tg_id"] == 5
