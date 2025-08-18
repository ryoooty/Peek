import sys
import types
from pathlib import Path
from datetime import datetime, timedelta, timezone

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

# cleanup
del sys.modules["app.config"]

def test_expire_old_topups(tmp_path):
    storage.init(tmp_path / "db.sqlite")
    storage.ensure_user(1, "u1")
    storage.ensure_user(2, "u2")
    t1 = storage.create_topup_pending(1, 10.0, "manual")
    t2 = storage.create_topup_pending(2, 20.0, "manual")
    t3 = storage.create_topup_pending(1, 5.0, "manual")

    old_ts = datetime.now(timezone.utc) - timedelta(hours=5)
    ts_str = old_ts.strftime("%Y-%m-%d %H:%M:%S")
    storage._exec(
        "UPDATE topups SET status='waiting_receipt', created_at=? WHERE id=?",
        (ts_str, t1),
    )
    storage._exec(
        "UPDATE topups SET created_at=? WHERE id=?",
        (ts_str, t2),
    )

    uids = storage.expire_old_topups(4)
    assert set(uids) == {1, 2}
    rows = storage.query("SELECT id FROM topups")
    remaining = {r["id"] for r in rows}
    assert remaining == {t3}
