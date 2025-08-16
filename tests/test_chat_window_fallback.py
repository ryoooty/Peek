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


def test_cb_set_chat_win_handles_unknown_window(tmp_path, monkeypatch):
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

    async def dummy_cb_set_chat(call):
        dummy_cb_set_chat.called = True
    dummy_cb_set_chat.called = False
    monkeypatch.setattr(profile, "cb_set_chat", dummy_cb_set_chat)

    storage.init(tmp_path / "db.sqlite")
    storage.ensure_user(1, "tester")
    storage._exec("ALTER TABLE users ADD COLUMN pro_window_local TEXT")
    storage._exec("ALTER TABLE users ADD COLUMN pro_window_utc TEXT")
    storage.set_user_field(1, "pro_window_local", "25:00-26:00")

    call = SimpleNamespace(from_user=SimpleNamespace(id=1))

    asyncio.run(profile.cb_set_chat_win(call))

    u = storage.get_user(1)
    assert u["pro_window_local"] == "09:00-21:00"
    assert u["pro_window_utc"] == "06:00-18:00"
    assert dummy_cb_set_chat.called
