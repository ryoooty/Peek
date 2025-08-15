import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))


class DummyLimits:
    auto_compress_default = False


class DummySettings:
    def __init__(self):
        self.default_model = "ghost"
        self.limits = DummyLimits()
        self.model_tariffs = {}


def test_profile_text_placeholder(monkeypatch):
    config_module = types.ModuleType("app.config")
    config_module.settings = DummySettings()
    config_module.BASE_DIR = ROOT
    config_module.register_reload_hook = lambda fn: None
    monkeypatch.setitem(sys.modules, "app.config", config_module)

    scheduler_module = types.ModuleType("app.scheduler")
    scheduler_module.rebuild_user_jobs = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "app.scheduler", scheduler_module)

    from app.handlers.profile import _profile_text

    text = _profile_text({})

    assert "Подписка: <b>free</b>" in text
    assert "Модель: <b>ghost</b>" in text
    assert "Всего сообщений: <b>0</b>" in text
    assert "Всего чатов: <b>0</b>" in text
    assert "Топ персонаж: <b>—</b>" in text

