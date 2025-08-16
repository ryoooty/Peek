import sys
import types
import asyncio
from pathlib import Path
from types import SimpleNamespace
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))


class Tariff:
    def __init__(self, input_per_1k: float = 1.0, output_per_1k: float = 1.0, cache_per_1k: float = 0.5):
        self.input_per_1k = input_per_1k
        self.output_per_1k = output_per_1k
        self.cache_per_1k = cache_per_1k


class DummyLimits:
    auto_compress_default = False


class DummySettings:
    def __init__(self):
        self.default_model = "ghost"
        self.model_tariffs = {"model-a": Tariff()}
        self.limits = DummyLimits()


def _setup(monkeypatch):
    config_module = types.ModuleType("app.config")
    config_module.settings = DummySettings()
    config_module.BASE_DIR = ROOT
    config_module.register_reload_hook = lambda fn: None
    monkeypatch.setitem(sys.modules, "app.config", config_module)
    sys.modules.pop("app.storage", None)
    sys.modules.pop("app.handlers.profile", None)

    scheduler_module = types.ModuleType("app.scheduler")
    scheduler_module.rebuild_user_jobs = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "app.scheduler", scheduler_module)

    import importlib
    monkeypatch.delitem(sys.modules, "app.storage", raising=False)
    monkeypatch.delitem(sys.modules, "app.handlers.profile", raising=False)
    storage = importlib.import_module("app.storage")
    profile = importlib.import_module("app.handlers.profile")

    async def dummy_safe_edit_text(message, text, **kwargs):
        await message.edit_text(text, **kwargs)

    monkeypatch.setattr(profile, "safe_edit_text", dummy_safe_edit_text)

    return storage, profile


class DummyMessage:
    def __init__(self, user_id: int):
        self.from_user = SimpleNamespace(id=user_id)
        self.edited: list[str] = []

    async def edit_text(self, text: str, **kwargs):
        self.edited.append(text)


class DummyCall:
    def __init__(self, user_id: int):
        self.from_user = SimpleNamespace(id=user_id)
        self.message = DummyMessage(user_id)
        self.answered: list[str] = []

    async def answer(self, text: str, *args, **kwargs):
        self.answered.append(text)


def test_cb_mode_updates_user_and_chats(tmp_path, monkeypatch):
    storage, profile = _setup(monkeypatch)

    storage.init(tmp_path / "db.sqlite")
    storage.ensure_user(1, "tester")
    char_id = storage.ensure_character("Tester")
    chat1 = storage.create_chat(1, char_id, mode="rp")
    chat2 = storage.create_chat(1, char_id, mode="rp")

    call = DummyCall(1)
    asyncio.run(profile.cb_mode(call))

    u = storage.get_user(1)
    assert u["default_chat_mode"] == "chat"
    assert storage.get_chat(chat1)["mode"] == "chat"
    assert storage.get_chat(chat2)["mode"] == "chat"
    assert call.answered == ["Режим обновлён"]
    assert call.message.edited

    call2 = DummyCall(1)
    asyncio.run(profile.cb_mode(call2))

    u = storage.get_user(1)
    assert u["default_chat_mode"] == "rp"
    assert storage.get_chat(chat1)["mode"] == "rp"
    assert storage.get_chat(chat2)["mode"] == "rp"
    assert call2.answered == ["Режим обновлён"]
    assert call2.message.edited
