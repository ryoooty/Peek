import sys
import types
import asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

# minimal config
class DummyLimits:
    context_threshold_tokens = 0
    auto_compress_default = False
    request_timeout_seconds = 60

class DummySettings:
    def __init__(self):
        self.default_model = "gpt-4o-mini"
        self.model_tariffs = {}
        self.toki_spend_coeff = 1.0
        self.limits = DummyLimits()

config_module = types.ModuleType("app.config")
config_module.settings = DummySettings()
config_module.BASE_DIR = ROOT
config_module.register_reload_hook = lambda fn: None
sys.modules["app.config"] = config_module

# reload storage and chats with dummy config
sys.modules.pop("app.storage", None)
sys.modules.pop("app.domain.chats", None)
from app import storage
from app.domain import chats
from app.config import settings

if not hasattr(chats, "_size_caps"):
    def _size_caps(_: str) -> tuple[int, int]:
        return chats.DEFAULT_TOKENS_LIMIT, 0
    chats._size_caps = _size_caps

del sys.modules["app.config"]


def setup_chat(tmp_path):
    storage.init(tmp_path / "db.sqlite")
    uid = 1
    storage.ensure_user(uid, "u")
    char_id = storage.ensure_character("C")
    chat_id = storage.create_chat(uid, char_id)
    return uid, chat_id


def test_chat_turn_skips_provider_on_zero_balance(tmp_path, monkeypatch):
    uid, chat_id = setup_chat(tmp_path)
    called = {"v": False}

    async def fake_provider_chat(*args, **kwargs):
        called["v"] = True
        return chats.ChatReply(text="ok", usage_in=1, usage_out=1)

    monkeypatch.setattr(chats, "provider_chat", fake_provider_chat)

    reply = asyncio.run(chats.chat_turn(uid, chat_id, "hi"))
    assert "попол" in reply.text.lower()
    assert not called["v"]


def test_live_stream_skips_provider_on_zero_balance(tmp_path, monkeypatch):
    uid, chat_id = setup_chat(tmp_path)
    called = {"v": False}

    async def fake_provider_stream(*args, **kwargs):
        called["v"] = True
        if False:
            yield {}

    monkeypatch.setattr(chats, "provider_stream", fake_provider_stream)

    async def collect():
        res = []
        async for ev in chats.live_stream(uid, chat_id, "hi"):
            res.append(ev)
        return res

    events = asyncio.run(collect())
    assert not called["v"]
    assert events and events[0]["kind"] == "final"
    assert "попол" in events[0].get("text", "").lower()
