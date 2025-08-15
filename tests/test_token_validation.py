import sys
import types
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

# Minimal config stub required by storage
class DummySettings:
    def __init__(self):
        self.subs = types.SimpleNamespace(nightly_toki_bonus={})

config_module = types.ModuleType("config")
config_module.settings = DummySettings()
sys.modules["app.config"] = config_module

from app import storage

# Clean up stub so it doesn't affect other tests
del sys.modules["app.config"]


def test_add_toki_negative_raises(tmp_path):
    storage.init(tmp_path / "toki.db")
    storage.ensure_user(1, "u")
    with pytest.raises(ValueError):
        storage.add_toki(1, -1)


def test_add_paid_tokens_negative_raises(tmp_path):
    storage.init(tmp_path / "paid.db")
    storage.ensure_user(1, "u")
    with pytest.raises(ValueError):
        storage.add_paid_tokens(1, -1)
