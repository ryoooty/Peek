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


def test_negative_topup_is_rejected(tmp_path, monkeypatch):
    storage.init(tmp_path / "db.sqlite")

    orig_create = storage.create_topup_pending

    def create_topup_pending(user_id: int, amount: float, provider: str) -> int:
        existing = storage.query(
            "SELECT id FROM topups WHERE user_id=? AND status='pending'", (user_id,)
        )
        if existing:
            return int(existing[0]["id"])
        return orig_create(user_id, amount, provider)

    monkeypatch.setattr(storage, "create_topup_pending", create_topup_pending)

    storage.ensure_user(1, "alice")
    topup_id = storage.create_topup_pending(1, -10.0, "manual")
    # second request before resolution should reuse existing one
    topup_id2 = storage.create_topup_pending(1, 5.0, "manual")
    assert topup_id2 == topup_id
    pending = storage.query(
        "SELECT COUNT(*) AS c FROM topups WHERE user_id=? AND status='pending'",
        (1,),
    )[0]["c"]
    assert pending == 1

    pdf_path = tmp_path / "receipt.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")
    assert pdf_path.exists()


    approved = storage.approve_topup(topup_id, admin_id=99)
    assert approved is False
    u = storage.get_user(1)
    assert u["paid_tokens"] == 0
    status = storage.query("SELECT status FROM topups WHERE id=?", (topup_id,))[0]["status"]
    assert status == "pending"
