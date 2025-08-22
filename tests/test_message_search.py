import asyncio
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

# Stub config to provide minimal settings
config_module = types.ModuleType("config")
config_module.BASE_DIR = ROOT

class DummySettings:
    def __init__(self):
        self.default_model = "gpt-4o-mini"
        self.limits = types.SimpleNamespace(context_threshold_tokens=0)

config_module.settings = DummySettings()
sys.modules["app.config"] = config_module

from app import storage
from app.domain import chats
from app.config import settings

del sys.modules["app.config"]


def test_search_messages_and_context(tmp_path: Path):
    storage.init(tmp_path / "db.sqlite")
    storage.ensure_user(1, "user")
    char_id = int(
        storage._exec("INSERT INTO characters(name) VALUES (?)", ("Char",)).lastrowid
    )
    chat_id = storage.create_chat(1, char_id)
    storage.add_message(chat_id, is_user=True, content="I love pizza")
    storage.add_message(chat_id, is_user=False, content="What else?")

    hits = storage.search_messages(chat_id, "pizza", limit=5)
    assert hits and "pizza" in hits[0]["content"]

    ctx = asyncio.run(
        chats._collect_context(
            chat_id,
            user_id=1,
            model=settings.default_model,
            limit=1,
            query="pizza",
        )
    )
    texts = [m["content"] for m in ctx]
    assert any("pizza" in t for t in texts)


def test_search_messages_special_chars(tmp_path: Path):
    storage.init(tmp_path / "db.sqlite")
    storage.ensure_user(1, "user")
    char_id = int(
        storage._exec("INSERT INTO characters(name) VALUES (?)", ("Char",)).lastrowid
    )
    chat_id = storage.create_chat(1, char_id)
    storage.add_message(chat_id, is_user=True, content="I love pizza")

    for q in ['"', '*']:
        assert storage.search_messages(chat_id, q) == []
