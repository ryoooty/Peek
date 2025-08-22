import asyncio
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

# Minimal config with a low context threshold
config_module = types.ModuleType("config")
config_module.BASE_DIR = ROOT


class DummyLimits:
    context_threshold_tokens = 50
    auto_compress_default = False
    request_timeout_seconds = 60


class DummySettings:
    def __init__(self):
        self.default_model = "gpt-4o-mini"
        self.model_tariffs = {}
        self.toki_spend_coeff = 1.0
        self.limits = DummyLimits()


config_module.settings = DummySettings()
sys.modules["app.config"] = config_module

sys.modules.pop("app.storage", None)
sys.modules.pop("app.domain.chats", None)
from app import storage  # noqa: E402
from app.domain import chats  # noqa: E402
from app.config import settings  # noqa: E402

del sys.modules["app.config"]


def test_history_size_bounded(tmp_path, monkeypatch):
    storage.init(tmp_path / "db.sqlite")
    storage.ensure_user(1, "user")
    monkeypatch.setattr(chats.settings.limits, "context_threshold_tokens", 50, raising=False)
    monkeypatch.setattr(chats.settings.limits, "auto_compress_default", False, raising=False)

    char_id = int(
        storage._exec("INSERT INTO characters(name) VALUES (?)", ("Char",)).lastrowid
    )
    chat_id = storage.create_chat(1, char_id)

    async def fake_summary(chat_id, model, sentences=4):
        return chats.ChatReply(text="summary", usage_in=0, usage_out=0)

    monkeypatch.setattr(chats, "summarize_chat", fake_summary)

    # Send many messages to trigger compression repeatedly
    for i in range(100):
        storage.add_message(chat_id, is_user=True, content=("msg" + str(i)) * 20)
        asyncio.run(
            chats._collect_context(chat_id, user_id=1, model=settings.default_model)
        )

    msgs = storage.list_messages(chat_id)
    assert len(msgs) <= 30
    assert sum(1 for m in msgs if m["content"] == "summary") == 1

