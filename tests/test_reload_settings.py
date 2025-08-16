import importlib
import sys


def test_reload_settings_keeps_nested_models():
    sys.modules.pop("app.config", None)
    config = importlib.import_module("app.config")
    importlib.reload(config)
    from app.config import LimitsConfig, SubsConfig, reload_settings, settings

    reload_settings()
    assert isinstance(settings.limits, LimitsConfig)
    assert isinstance(settings.subs, SubsConfig)
