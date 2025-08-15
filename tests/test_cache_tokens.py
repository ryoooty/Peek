import sys
import types
import asyncio
from pathlib import Path
import pytest

# Stub configuration before importing modules that depend on it
class Tariff:
    def __init__(self, input_per_1k: float, output_per_1k: float, cache_per_1k: float):
        self.input_per_1k = input_per_1k
        self.output_per_1k = output_per_1k
        self.cache_per_1k = cache_per_1k


class DummyLimits:
    context_threshold_tokens = 0
    auto_compress_default = False
    request_timeout_seconds = 60


class DummySettings:
    def __init__(self):
        self.default_model = "gpt-4o-mini"
        self.model_tariffs = {
            "gpt-4o-mini": Tariff(1.0, 1.0, 0.5),
            "gpt-4o": Tariff(2.0, 2.0, 1.0),
            "deepseek-chat": Tariff(0.6, 0.6, 0.3),
            "deepseek-reasoner": Tariff(1.2, 1.2, 0.6),
        }
        self.limits = DummyLimits()
        self.deepseek_base_url = ""
        self.deepseek_api_key = None
        self.toki_spend_coeff = 1.0



ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

config_module = types.ModuleType("config")
config_module.settings = DummySettings()
sys.modules["app.config"] = config_module
from app import storage
from app.domain import chats


class DummyResp:
    def __init__(self, text: str, usage_in: int, usage_out: int):
        self.text = text
        self.usage_in = usage_in
        self.usage_out = usage_out


def test_chat_turn_accumulates_cache_tokens(tmp_path, monkeypatch):
    storage.init(tmp_path / "chat.db")
    storage.ensure_user(1, "u")
    char_id = storage.ensure_character("c")
    chat_id = storage.create_chat(1, char_id)

    async def _collect_ctx(chat_id, **kwargs):
        return []
    monkeypatch.setattr(chats, "_collect_context", _collect_ctx)

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(chats, "_maybe_compress_history", noop)

    calls = [(3, 7), (2, 1)]

    async def fake_chat(*args, **kwargs):
        inp, out = calls.pop(0)
        return DummyResp("ok", inp, out)

    monkeypatch.setattr(chats, "provider_chat", fake_chat)

    asyncio.run(chats.chat_turn(1, chat_id, "hi"))
    asyncio.run(chats.chat_turn(1, chat_id, "hi"))

    assert storage.get_chat_cache_tokens(chat_id) == (3 + 7) + (2 + 1)


def test_chat_stream_accumulates_cache_tokens(tmp_path, monkeypatch):
    storage.init(tmp_path / "stream.db")
    storage.ensure_user(2, "u")
    char_id = storage.ensure_character("c")
    chat_id = storage.create_chat(2, char_id)

    async def _collect_ctx(chat_id, **kwargs):
        return []
    monkeypatch.setattr(chats, "_collect_context", _collect_ctx)

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(chats, "_maybe_compress_history", noop)

    async def fake_stream(*args, **kwargs):
        yield {"type": "delta", "text": "foo"}
        yield {"type": "usage", "in": 5, "out": 7}

    monkeypatch.setattr(chats, "provider_stream", fake_stream)

    asyncio.run(_consume_stream(chats.live_stream(2, chat_id, "hi")))


    assert storage.get_chat_cache_tokens(chat_id) == 5 + 7


async def _consume_stream(gen):
    async for _ in gen:
        pass


def test_cache_tokens_affect_billing(tmp_path, monkeypatch):
    storage.init(tmp_path / "bill.db")
    storage.ensure_user(3, "u")
    storage.add_toki(3, 100)
    char_id = storage.ensure_character("c")
    chat_id = storage.create_chat(3, char_id)

    async def _collect_ctx(chat_id, **kwargs):
        return []
    monkeypatch.setattr(chats, "_collect_context", _collect_ctx)

    async def noop(*args, **kwargs):
        return None
    monkeypatch.setattr(chats, "_maybe_compress_history", noop)

    calls = [(1000, 0), (0, 0)]

    async def fake_chat(*args, **kwargs):
        inp, out = calls.pop(0)
        return DummyResp("ok", inp, out)

    monkeypatch.setattr(chats, "provider_chat", fake_chat)

    r1 = asyncio.run(chats.chat_turn(3, chat_id, "hi"))
    assert r1.billed == 1
    r2 = asyncio.run(chats.chat_turn(3, chat_id, "hi"))
    assert r2.billed == 1  # billed solely for cached tokens


def teardown_module():
    sys.modules.pop("app.storage", None)
    sys.modules.pop("app.domain.chats", None)
    sys.modules.pop("app.handlers.profile", None)
    cfg = types.ModuleType("app.config")
    cfg.settings = DummySettings()
    cfg.settings.model_tariffs = {"model-a": Tariff(1.0, 1.0, 0.5), "model-b": Tariff(1.0, 1.0, 0.5)}
    sys.modules["app.config"] = cfg


def test_collect_context_compression_updates_cache(tmp_path, monkeypatch):
    storage.init(tmp_path / "ctx.db")
    storage.ensure_user(4, "u")
    char_id = storage.ensure_character("c")
    chat_id = storage.create_chat(4, char_id)
    storage.add_message(chat_id, is_user=True, content="x" * 200)

    config_module.settings.limits.context_threshold_tokens = 10
    storage.add_chat_cache_tokens(chat_id, 100)

    async def fake_summary(chat_id, model):
        return chats.ChatReply(text="s", usage_in=3, usage_out=7)

    monkeypatch.setattr(chats, "summarize_chat", fake_summary)
    monkeypatch.setattr(chats, "_apply_billing", lambda *a, **k: (0, 0))

    asyncio.run(chats._collect_context(chat_id, user_id=4, model="gpt-4o-mini"))

    assert storage.get_chat_cache_tokens(chat_id) == 100 - 3 + 7


def test_maybe_compress_history_updates_cache(tmp_path, monkeypatch):
    storage.init(tmp_path / "hist.db")
    storage.ensure_user(5, "u")
    char_id = storage.ensure_character("c")
    chat_id = storage.create_chat(5, char_id)
    storage.add_message(chat_id, is_user=True, content="y" * 200)

    config_module.settings.limits.context_threshold_tokens = 10
    config_module.settings.limits.auto_compress_default = True
    storage.add_chat_cache_tokens(chat_id, 50)

    async def fake_summary(chat_id, model):
        return chats.ChatReply(text="s", usage_in=5, usage_out=2)

    monkeypatch.setattr(chats, "summarize_chat", fake_summary)
    monkeypatch.setattr(chats, "_apply_billing", lambda *a, **k: (0, 0))

    asyncio.run(chats._maybe_compress_history(5, chat_id, "gpt-4o-mini"))

    assert storage.get_chat_cache_tokens(chat_id) == 50 - 5 + 2

