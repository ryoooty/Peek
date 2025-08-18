import asyncio
import sys
import types
from types import SimpleNamespace

class DummyLimits:
    rate_limit_seconds = 0
    request_timeout_seconds = 60
    request_attempts = 1


class DummySettings:
    def __init__(self):
        self.deepseek_base_url = ""
        self.deepseek_api_key = None
        self.limits = DummyLimits()


config_module = types.ModuleType("config")
config_module.settings = DummySettings()
sys.modules["app.config"] = config_module

from app.providers import deepseek_openai as provider


def test_chat_rate_limit(monkeypatch):
    events = []

    class DummyResp:
        def __init__(self):
            self._data = {"choices": [{"message": {"content": "ok"}}], "usage": {}}
            self.status = 200
            self.status = 200

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

        def post(self, *args, **kwargs):
            events.append("post")
            return DummyResp()

    class DummyAiohttp:
        ClientTimeout = lambda **kw: None
        ClientSession = DummySession

    limits = SimpleNamespace(rate_limit_seconds=1, request_timeout_seconds=60, request_attempts=1)
    settings = SimpleNamespace(deepseek_base_url="", deepseek_api_key=None, limits=limits)
    monkeypatch.setattr(provider, "settings", settings)
    monkeypatch.setattr(provider, "aiohttp", DummyAiohttp)
    orig_sleep = asyncio.sleep
    monkeypatch.setattr(provider, "_rate_limiter", asyncio.Semaphore(1))

    async def fake_sleep(delay):
        events.append("sleep")
        await orig_sleep(0)

    monkeypatch.setattr(provider.asyncio, "sleep", fake_sleep)

    async def run():
        await asyncio.gather(
            provider.chat(model="m", messages=[]),
            provider.chat(model="m", messages=[]),
        )

    asyncio.run(run())

    assert events[:3] == ["post", "sleep", "post"]


def test_stream_rate_limit(monkeypatch):
    events = []
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
            events.append("post")
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
            return DummyPost()

    class DummyAiohttp:
        ClientTimeout = lambda **kw: None
        ClientSession = DummySession

    limits = SimpleNamespace(rate_limit_seconds=1, request_timeout_seconds=60, request_attempts=1)
    settings = SimpleNamespace(deepseek_base_url="", deepseek_api_key=None, limits=limits)
    monkeypatch.setattr(provider, "settings", settings)
    monkeypatch.setattr(provider, "aiohttp", DummyAiohttp)
    orig_sleep = asyncio.sleep
    monkeypatch.setattr(provider, "_rate_limiter", asyncio.Semaphore(1))

    async def fake_sleep(delay):
        events.append("sleep")
        await orig_sleep(0)

    monkeypatch.setattr(provider.asyncio, "sleep", fake_sleep)

    async def _collect():
        return [chunk async for chunk in provider.stream_chat(model="m", messages=[])]

    async def run():
        await asyncio.gather(
            _collect(),
            _collect(),
        )

    asyncio.run(run())

    assert events[:3] == ["post", "sleep", "post"]


def test_max_concurrent_requests(monkeypatch):
    events = []
    blocker = asyncio.Event()

    class DummyResp:
        def __init__(self):
            self._data = {"choices": [{"message": {"content": "ok"}}], "usage": {}}
            self.status = 200

        async def json(self):
            await blocker.wait()
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

        def post(self, *args, **kwargs):
            events.append("post")
            return DummyResp()

    class DummyAiohttp:
        ClientTimeout = lambda **kw: None
        ClientSession = DummySession

    limits = SimpleNamespace(
        rate_limit_seconds=1,
        request_timeout_seconds=60,
        request_attempts=1,
        max_concurrent_requests=10,
    )
    settings = SimpleNamespace(deepseek_base_url="", deepseek_api_key=None, limits=limits)
    monkeypatch.setattr(provider, "settings", settings)
    monkeypatch.setattr(provider, "aiohttp", DummyAiohttp)
    monkeypatch.setattr(
        provider, "_rate_limiter", asyncio.Semaphore(settings.limits.max_concurrent_requests)
    )

    orig_sleep = asyncio.sleep

    async def fake_sleep(delay):
        await orig_sleep(0)

    monkeypatch.setattr(provider.asyncio, "sleep", fake_sleep)

    async def run():
        tasks = [
            asyncio.create_task(provider.chat(model="m", messages=[]))
            for _ in range(11)
        ]
        await asyncio.sleep(0)
        assert len(events) == 10
        blocker.set()
        await asyncio.gather(*tasks)

    asyncio.run(run())

    assert len(events) == 11
