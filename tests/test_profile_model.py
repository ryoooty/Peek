import sys
import types
import asyncio
from pathlib import Path
from types import SimpleNamespace

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
        self.model_tariffs = {
            "model-a": Tariff(),
            "model-b": Tariff(),
        }
        self.limits = DummyLimits()


def test_cb_model_handles_unknown_current_model(tmp_path, monkeypatch):
    config_module = types.ModuleType("app.config")
    config_module.settings = DummySettings()
    config_module.BASE_DIR = ROOT
    config_module.register_reload_hook = lambda fn: None
    monkeypatch.setitem(sys.modules, "app.config", config_module)

    scheduler_module = types.ModuleType("app.scheduler")
    scheduler_module.rebuild_user_jobs = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "app.scheduler", scheduler_module)

    from app import storage
    from app.handlers import profile

    async def dummy_safe_edit_text(message, text, **kwargs):
        await message.edit_text(text, **kwargs)
    monkeypatch.setattr(profile, "safe_edit_text", dummy_safe_edit_text)

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

    storage.init(tmp_path / "db.sqlite")
    storage.ensure_user(1, "tester")
    storage.set_user_field(1, "default_model", "unknown-model")

    call = DummyCall(1)
    asyncio.run(profile.cb_model(call))

    u = storage.get_user(1)
    assert u["default_model"] == "model-b"
    assert call.answered == ["Модель обновлена"]
    assert call.message.edited
