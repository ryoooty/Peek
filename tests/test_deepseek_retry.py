import asyncio
import sys
import types


class DummyLimits:
    request_timeout_seconds = 60
    request_attempts = 3


class DummySettings:
    def __init__(self):
        self.deepseek_base_url = ""
        self.deepseek_api_key = None
        self.limits = DummyLimits()


config_module = types.ModuleType("config")
config_module.settings = DummySettings()
sys.modules["app.config"] = config_module

from app.providers import deepseek_openai as provider


def test_chat_retries(monkeypatch):
    attempts = {"count": 0}
    fail_times = 2

    class DummyResp:
        def __init__(self):
            self._data = {
                "choices": [{"message": {"content": "hello"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 2},
            }

        async def json(self):
            return self._data

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

    class DummySession:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        def post(self, url, headers=None, json=None):
            attempts["count"] += 1
            if attempts["count"] <= fail_times:
                raise RuntimeError("fail")
            return DummyResp()

    class DummyAiohttp:
        ClientTimeout = lambda **kw: None
        ClientSession = DummySession

    async def fake_sleep(_):
        return None

    dummy_limits = types.SimpleNamespace(request_timeout_seconds=60, request_attempts=3)
    dummy_settings = types.SimpleNamespace(
        deepseek_base_url="", deepseek_api_key=None, limits=dummy_limits
    )
    monkeypatch.setattr(provider, "settings", dummy_settings)
    monkeypatch.setattr(provider, "aiohttp", DummyAiohttp)
    monkeypatch.setattr(provider.asyncio, "sleep", fake_sleep)

    r = asyncio.run(provider.chat(model="m", messages=[{"role": "user", "content": "hi"}]))
    assert r.text == "hello"
    assert attempts["count"] == 3


def test_stream_chat_retries(monkeypatch):
    attempts = {"count": 0}
    fail_times = 1

    lines = [
        b"data: {\"choices\":[{\"delta\":{\"content\":\"hi\"}}]}\n",
        b"data: {\"usage\":{\"prompt_tokens\":1,\"completion_tokens\":2}}\n",
        b"data: [DONE]\n",
    ]

    class DummyStreamResp:
        def __init__(self):
            async def gen():
                for l in lines:
                    yield l

            self.content = gen()

    class DummyPost:
        async def __aenter__(self):
            return DummyStreamResp()

        async def __aexit__(self, exc_type, exc, tb):
            pass

    class DummySession:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        def post(self, *args, **kwargs):
            attempts["count"] += 1
            if attempts["count"] <= fail_times:
                raise RuntimeError("boom")
            return DummyPost()

    class DummyAiohttp:
        ClientTimeout = lambda **kw: None
        ClientSession = DummySession

    async def fake_sleep(_):
        return None

    dummy_limits = types.SimpleNamespace(request_timeout_seconds=60, request_attempts=2)
    dummy_settings = types.SimpleNamespace(
        deepseek_base_url="", deepseek_api_key=None, limits=dummy_limits
    )
    monkeypatch.setattr(provider, "settings", dummy_settings)
    monkeypatch.setattr(provider, "aiohttp", DummyAiohttp)
    monkeypatch.setattr(provider.asyncio, "sleep", fake_sleep)

    async def run_stream():
        return [chunk async for chunk in provider.stream_chat(model="m", messages=[])]

    chunks = asyncio.run(run_stream())
    assert attempts["count"] == 2
    assert chunks == [
        {"type": "delta", "text": "hi"},
        {"type": "usage", "in": 1, "out": 2},
    ]

