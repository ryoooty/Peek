import pytest

from app import storage


def test_create_chat_inserts_row(tmp_path):
    """create_chat returns inserted row id and row exists."""
    storage.init(tmp_path / "db.sqlite")
    storage.ensure_user(1, "test")
    char_id = int(
        storage._exec("INSERT INTO characters(name) VALUES (?)", ("Char",)).lastrowid
    )

    chat_id = storage.create_chat(1, char_id)

    assert isinstance(chat_id, int)

    row = storage._q("SELECT user_id, char_id FROM chats WHERE id=?", (chat_id,)).fetchone()
    assert row is not None
    assert row["user_id"] == 1
    assert row["char_id"] == char_id
