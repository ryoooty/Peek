import sys
import types
import asyncio
from pathlib import Path
from types import SimpleNamespace
import inspect

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))


class DummyLimits:
    auto_compress_default = False


class DummySettings:
    def __init__(self):
        self.default_model = "ghost"
        self.model_tariffs = {"model-a": object()}
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

    async def answer(self, text: str = "", *args, **kwargs):
        self.answered.append(text)

def test_profile_kb_contains_subscription_button(monkeypatch):
    _, profile = _setup(monkeypatch)
    source = inspect.getsource(profile._profile_kb)
    assert 'callback_data="prof:sub"' in source


def test_cb_sub_renders_subscription_screen(tmp_path, monkeypatch):
    storage, profile = _setup(monkeypatch)
    storage.init(tmp_path / "db.sqlite")
    storage.ensure_user(1, "tester")
    call = DummyCall(1)
    asyncio.run(profile.cb_sub(call))
    assert call.message.edited
    assert "Подписка" in call.message.edited[0]
