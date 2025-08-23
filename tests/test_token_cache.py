import types
import asyncio

from app.domain import chats as chats_module


WARNING_TEXT = "⚠ Баланс токенов на нуле. Пополните баланс, чтобы продолжить комфортно."


class DummyResp:
    text = "hi"
    usage_in = 20
    usage_out = 30


def _fake_settings():
    return types.SimpleNamespace(
        default_model="m",
        toki_spend_coeff=1,
        limits=types.SimpleNamespace(
            request_timeout_seconds=30,
            context_threshold_tokens=0,
            auto_compress_default=False,
        ),
    )


def test_chat_turn_no_tokens_returns_warning(monkeypatch):
    class DummyStorage:
        def get_user(self, user_id):
            return {"free_toki": 0, "paid_tokens": 0, "default_model": "m"}

        def get_chat(self, chat_id):
            return {}

        def get_cached_tokens(self, chat_id):
            return 0

    storage = DummyStorage()
    monkeypatch.setattr(chats_module, "storage", storage)
    monkeypatch.setattr(chats_module, "settings", _fake_settings())
    monkeypatch.setattr(chats_module, "_size_caps", lambda size: (700, 0), raising=False)

    async def boom(**kwargs):
        raise AssertionError("provider should not be called")

    monkeypatch.setattr(chats_module, "provider_chat", boom)

    r = asyncio.run(chats_module.chat_turn(1, 1, "hi"))
    assert r.deficit == 1
    assert r.text == WARNING_TEXT


def test_chat_turn_uses_cached_tokens(monkeypatch):
    class DummyStorage:
        def __init__(self):
            self.cached = None
            self.spent = None

        def get_user(self, user_id):
            return {"free_toki": 100, "paid_tokens": 0, "default_model": "m"}

        def get_chat(self, chat_id):
            return {}

        def get_cached_tokens(self, chat_id):
            return 10

        def set_cached_tokens(self, chat_id, amount):
            self.cached = amount

        def spend_tokens(self, user_id, amount):
            self.spent = amount
            return (0, 0, 0)

        def list_messages(self, chat_id, limit=50):
            return []

        def search_messages(self, chat_id, query, limit=5):
            return []

    storage = DummyStorage()
    monkeypatch.setattr(chats_module, "storage", storage)
    monkeypatch.setattr(chats_module, "settings", _fake_settings())

    async def fake_provider_chat(**kwargs):
        return DummyResp()

    monkeypatch.setattr(chats_module, "provider_chat", fake_provider_chat)

    def fake_usage_to_toki(model, in_tokens, out_tokens, cached_tokens):
        # bill only the delta over cached_tokens
        return in_tokens + out_tokens - cached_tokens

    monkeypatch.setattr(chats_module, "usage_to_toki", fake_usage_to_toki)
    async def _noop(*args, **kwargs):
        return None

    async def _collect(*args, **kwargs):
        return []

    monkeypatch.setattr(chats_module, "_maybe_compress_history", _noop)
    monkeypatch.setattr(chats_module, "_collect_context", _collect)

    r = asyncio.run(chats_module.chat_turn(1, 1, "hello"))

    assert r.text == "hi"
    assert storage.cached == 50  # 20 + 30
    assert storage.spent == 40  # delta 40 billed


def test_live_stream_no_tokens(monkeypatch):
    class DummyStorage:
        def get_user(self, user_id):
            return {"free_toki": 0, "paid_tokens": 0, "default_model": "m"}

        def get_chat(self, chat_id):
            return {}

        def get_cached_tokens(self, chat_id):
            return 0

    storage = DummyStorage()
    monkeypatch.setattr(chats_module, "storage", storage)
    monkeypatch.setattr(chats_module, "settings", _fake_settings())
    monkeypatch.setattr(
        chats_module, "_size_caps", lambda size: (700, 0), raising=False
    )

    async def boom(**kwargs):
        raise AssertionError("stream should not start")

    monkeypatch.setattr(chats_module, "provider_stream", boom)

    async def run():
        res = []
        async for ev in chats_module.live_stream(1, 1, "hi"):
            res.append(ev)
        return res

    events = asyncio.run(run())
    assert events == [
        {
            "kind": "final",
            "text": WARNING_TEXT,
            "usage_in": "0",
            "usage_out": "0",
            "billed": "0",
            "deficit": "1",
        }
    ]
