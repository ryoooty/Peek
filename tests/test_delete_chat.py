import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

# Stub config with minimal settings
config_module = types.ModuleType("config")
config_module.BASE_DIR = ROOT


class DummySettings:
    def __init__(self):
        self.default_model = "gpt-4o-mini"
        self.limits = types.SimpleNamespace(context_threshold_tokens=0)


config_module.settings = DummySettings()
sys.modules["app.config"] = config_module

from app import storage

del sys.modules["app.config"]


def test_delete_chat_removes_proactive_entries(tmp_path: Path):
    storage.init(tmp_path / "db.sqlite")
    storage.ensure_user(1, "user")

    char_id = int(
        storage._exec("INSERT INTO characters(name) VALUES (?)", ("Char",)).lastrowid
    )
    chat_id = storage.create_chat(1, char_id)

    storage.add_message(chat_id, is_user=True, content="hi")

    storage._exec(
        "INSERT INTO proactive_plan(user_id,chat_id,fire_at,created_at) VALUES (?,?,?,?)",
        (1, chat_id, 0, 0),
    )
    storage._exec(
        "INSERT INTO proactive_log(user_id,chat_id,char_id,kind) VALUES (?,?,?,?)",
        (1, chat_id, char_id, "regular"),
    )

    assert storage.delete_chat(chat_id, 1)

    for table, column in [
        ("messages", "chat_id"),
        ("messages_fts", "chat_id"),
        ("chats", "id"),
        ("proactive_plan", "chat_id"),
        ("proactive_log", "chat_id"),
    ]:
        r = storage._q(
            f"SELECT COUNT(*) AS c FROM {table} WHERE {column}=?", (chat_id,)
        ).fetchone()
        assert int(r["c"] or 0) == 0

