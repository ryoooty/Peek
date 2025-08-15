import asyncio
import types

from app.providers import deepseek_openai as provider


def test_chat_non_200(monkeypatch):
    json_called = {"count": 0}

    class DummyResp:
        status = 500

        async def json(self):
            json_called["count"] += 1
            raise AssertionError("json should not be called")

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
            return DummyResp()

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

    r = asyncio.run(provider.chat(model="m", messages=[{"role": "user", "content": "hi"}]))
    assert r.text == provider.FALLBACK_TEXT
    assert json_called["count"] == 0
