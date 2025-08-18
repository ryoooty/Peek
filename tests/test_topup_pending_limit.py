import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))


class DummySettings:
    def __init__(self):
        self.subs = types.SimpleNamespace(nightly_toki_bonus={})


config_module = types.ModuleType("config")
config_module.BASE_DIR = ROOT
config_module.settings = DummySettings()
sys.modules["app.config"] = config_module

from app import storage

del sys.modules["app.config"]


def test_delete_pending_topup(tmp_path):
    storage.init(tmp_path / "db.sqlite")
    storage.ensure_user(1, "alice")
    tid = storage.create_topup_pending(1, 10.0, "manual")
    assert storage.has_pending_topup(1) is True
    assert storage.delete_topup(tid) is True
    assert storage.has_pending_topup(1) is False

