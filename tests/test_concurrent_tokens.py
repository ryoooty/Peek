import sys
import types
import threading
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

class DummySettings:
    toki_spend_coeff = 1.0

config_module = types.ModuleType("config")
config_module.settings = DummySettings()
config_module.BASE_DIR = ROOT
config_module.register_reload_hook = lambda fn: None
sys.modules["app.config"] = config_module

from app import storage


def test_concurrent_spend_never_negative(tmp_path):
    storage.init(tmp_path / "db.sqlite")
    storage.ensure_user(1, "test")
    storage.add_toki(1, 5)

    results = []

    def worker():
        while True:
            try:
                results.append(storage.spend_tokens(1, 1))
                break
            except sqlite3.OperationalError:
                continue

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    u = storage.get_user(1) or {}
    assert int(u.get("free_toki") or 0) >= 0
    assert int(u.get("paid_tokens") or 0) >= 0
    total_spent = sum(r[0] + r[1] for r in results)
    assert total_spent + int(u.get("free_toki") or 0) + int(u.get("paid_tokens") or 0) == 5
