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


def _setup(monkeypatch):
    config_module = types.ModuleType("config")
    config_module.settings = DummySettings()
    config_module.BASE_DIR = ROOT
    config_module.register_reload_hook = lambda fn: None
    monkeypatch.setitem(sys.modules, "app.config", config_module)

    import importlib
    monkeypatch.delitem(sys.modules, "app.storage", raising=False)
    monkeypatch.delitem(sys.modules, "app.domain.chats", raising=False)
    storage = importlib.import_module("app.storage")
    chats = importlib.import_module("app.domain.chats")

    # ensure cleanup after test
    monkeypatch.setitem(sys.modules, "app.storage", storage)
    monkeypatch.setitem(sys.modules, "app.domain.chats", chats)
    return storage, chats


class DummyResp:
    def __init__(self, text: str, usage_in: int, usage_out: int):
        self.text = text
        self.usage_in = usage_in
        self.usage_out = usage_out


def test_chat_turn_accumulates_cache_tokens(tmp_path, monkeypatch):
    storage, chats = _setup(monkeypatch)
    storage.init(tmp_path / "chat.db")
    storage.ensure_user(1, "u")
    char_id = int(storage._exec("INSERT INTO characters(name) VALUES (?)", ("Char",)).lastrowid)
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

    ch = storage.get_chat(chat_id) or {}
    assert int(ch.get("cache_tokens") or 0) == (3 + 7) + (2 + 1)


def test_live_stream_accumulates_cache_tokens(tmp_path, monkeypatch):
    storage, chats = _setup(monkeypatch)
    storage.init(tmp_path / "stream.db")
    storage.ensure_user(2, "u")
    char_id = int(storage._exec("INSERT INTO characters(name) VALUES (?)", ("Char",)).lastrowid)
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

    ch = storage.get_chat(chat_id) or {}
    assert int(ch.get("cache_tokens") or 0) == 5 + 7


async def _consume_stream(gen):
    async for _ in gen:
        pass


def test_cache_tokens_affect_billing(tmp_path, monkeypatch):
    storage, chats = _setup(monkeypatch)
    storage.init(tmp_path / "bill.db")
    storage.ensure_user(3, "u")
    storage.add_toki(3, 100)
    char_id = int(storage._exec("INSERT INTO characters(name) VALUES (?)", ("Char",)).lastrowid)
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

