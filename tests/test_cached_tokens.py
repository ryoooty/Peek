import os

os.environ.setdefault("BOT_TOKEN", "test-token")

from app import storage


def test_cached_tokens_get_set(tmp_path):
    storage.init(tmp_path / "db.sqlite")
    storage.ensure_user(1, "u1")
    char_id = int(storage._exec("INSERT INTO characters(name) VALUES (?)", ("Char",)).lastrowid)
    chat_id = storage.create_chat(1, char_id)
    assert storage.get_cached_tokens(chat_id) == 0
    storage.set_cached_tokens(chat_id, 42)
    assert storage.get_cached_tokens(chat_id) == 42
    ch = storage.get_chat(chat_id) or {}
    assert ch.get("cached_tokens") == 42
