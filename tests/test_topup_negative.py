import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

# Minimal config stub required by storage
class DummySettings:
    def __init__(self):
        self.subs = types.SimpleNamespace(nightly_toki_bonus={})

config_module = types.ModuleType("config")
config_module.BASE_DIR = ROOT
config_module.settings = DummySettings()
sys.modules["app.config"] = config_module

from app import storage

del sys.modules["app.config"]


def test_negative_topup_is_rejected(tmp_path):
    storage.init(tmp_path / "db.sqlite")
    storage.ensure_user(1, "alice")
    topup_id = storage.create_topup_pending(1, -10.0, "manual")
    approved = storage.approve_topup(topup_id, admin_id=99)
    assert approved is False
    u = storage.get_user(1)
    assert u["paid_tokens"] == 0
    status = storage.query("SELECT status FROM topups WHERE id=?", (topup_id,))[0]["status"]
    assert status == "pending"
