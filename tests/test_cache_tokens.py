import sys
from pathlib import Path
import types
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

class DummyMessage:
    def __init__(self, user_id: int):
        self.from_user = types.SimpleNamespace(id=user_id, username="u")
        self.sent = []
    async def answer(self, text: str):
        self.sent.append(text)

@pytest.mark.asyncio
async def test_chat_turn_accumulates_cache_tokens(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "x")
    from app import storage
    storage.init(tmp_path / "db.sqlite")
    storage.ensure_user(1, "test")
    char_id = storage.ensure_character("Tester")
    cur = storage._exec(
        "INSERT INTO chats(user_id,char_id,mode,resp_size,seq_no) VALUES (?,?,?,?,?)",
        (1, char_id, "rp", "auto", 1),
    )
    chat_id = int(cur.lastrowid)

    config_module = types.ModuleType("config")
    class Limits:
        request_timeout_seconds = 60
        context_threshold_tokens = 0
        auto_compress_default = False
    config_module.settings = types.SimpleNamespace(
        default_model="gpt-4o-mini",
        model_tariffs={
            "gpt-4o-mini": types.SimpleNamespace(input_per_1k=1.0, output_per_1k=1.0, cache_per_1k=0.5)
        },
        limits=Limits(),
    )
    sys.modules["app.config"] = config_module

    from app.domain import chats
    monkeypatch.setattr(chats, "_collect_context", lambda chat_id: [])
    async def fake_provider_chat(*args, **kwargs):
        return types.SimpleNamespace(text="hi", usage_in=7, usage_out=3)
    monkeypatch.setattr(chats, "provider_chat", fake_provider_chat)
    async def fake_compress(*args, **kwargs):
        return None
    monkeypatch.setattr(chats, "_maybe_compress_history", fake_compress)
    monkeypatch.setattr(chats, "_apply_billing", lambda *a, **kw: (0, 0))

    await chats.chat_turn(1, chat_id, "hello")
    u = storage.get_user(1) or {}
    assert int(u.get("cache_tokens") or 0) == 10

    from app.handlers.balance import cmd_balance
    msg = DummyMessage(1)
    await cmd_balance(msg)
    assert "Кэш‑токены: <code>10</code>" in msg.sent[0]

