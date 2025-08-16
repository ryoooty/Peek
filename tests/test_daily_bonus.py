import importlib
import os
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))


@pytest.fixture
def storage():
    config_module = types.ModuleType("config")
    config_module.BASE_DIR = ROOT

    class DummySettings:
        def __init__(self):
            self.subs = types.SimpleNamespace(nightly_toki_bonus={"free": 1000})

    config_module.settings = DummySettings()
    sys.modules["app.config"] = config_module
    sys.modules.pop("app.storage", None)
    storage_module = importlib.import_module("app.storage")
    importlib.reload(storage_module)
    yield storage_module
    storage_module.close()
    sys.modules.pop("app.storage", None)
    sys.modules.pop("app.config", None)


def test_migration_adds_last_daily_bonus_column(tmp_path, storage):
    storage.init(tmp_path / "db.sqlite")
    assert storage._has_col("users", "last_daily_bonus_at")


def test_daily_bonus_free_users_grants_tokens_and_sets_timestamp(tmp_path, storage):
    storage.init(tmp_path / "db2.sqlite")
    storage.ensure_user(1, "alice")
    u = storage.get_user(1)
    assert u["free_toki"] == 0
    assert u.get("last_daily_bonus_at") is None

    uids = storage.daily_bonus_free_users()
    assert 1 in uids

    u2 = storage.get_user(1)
    assert u2["free_toki"] == 1000
    assert u2.get("last_daily_bonus_at") is not None
