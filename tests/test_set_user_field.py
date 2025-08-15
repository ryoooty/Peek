import os
import pytest

# Provide mandatory environment variable for app.config
os.environ.setdefault("BOT_TOKEN", "test-token")

from app import storage


def test_set_user_field_validates_field(tmp_path):
    storage.init(tmp_path / "db.sqlite")
    storage.ensure_user(1, "u1")

    storage.set_user_field(1, "username", "new")
    assert storage.get_user(1)["username"] == "new"

    with pytest.raises(ValueError):
        storage.set_user_field(1, "not_allowed", "x")

    with pytest.raises(ValueError):
        storage.set_user_field(1, "username; DROP TABLE users; --", "x")


def test_set_user_field_prevents_sql_injection(tmp_path):
    storage.init(tmp_path / "db2.sqlite")
    storage.ensure_user(1, "u1")

    malicious = "name', subscription='pro"
    storage.set_user_field(1, "username", malicious)

    u = storage.get_user(1)
    assert u["username"] == malicious
    assert u["subscription"] == "free"

