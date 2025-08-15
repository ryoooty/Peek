import asyncio
import datetime as dt
import sys
import types

# Stubs for external packages
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
sys.modules.setdefault("pydantic", pydantic)

pydantic_settings = types.ModuleType("pydantic_settings")


class _BaseSettings:
    def __init__(self, *args, **kwargs):
        pass


def _SettingsConfigDict(**kwargs):
    return kwargs


pydantic_settings.BaseSettings = _BaseSettings
pydantic_settings.SettingsConfigDict = _SettingsConfigDict
sys.modules.setdefault("pydantic_settings", pydantic_settings)

# Provide minimal aiogram.Bot for scheduler import
aiogram = sys.modules.setdefault("aiogram", types.ModuleType("aiogram"))


class _StubBot:
    async def send_message(self, *args, **kwargs):
        pass


aiogram.Bot = _StubBot

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
