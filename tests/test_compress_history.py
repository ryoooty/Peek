import sqlite3
import pytest

from app import storage


def test_compress_history_rollback(tmp_path, monkeypatch):
    storage.init(tmp_path / "db.sqlite")
    storage.ensure_user(1, "u")
    char_id = storage._exec("INSERT INTO characters(name) VALUES (?)", ("Char",)).lastrowid
    chat_id = storage.create_chat(1, char_id)
    storage.add_message(chat_id, is_user=True, content="hi")
    before = storage.list_messages(chat_id)

    def fail_add_message(*args, **kwargs):
        raise sqlite3.IntegrityError("fail")

    monkeypatch.setattr(storage, "add_message", fail_add_message)

    with pytest.raises(sqlite3.IntegrityError):
        storage.compress_history(chat_id, "summary")

    assert storage.list_messages(chat_id) == before
