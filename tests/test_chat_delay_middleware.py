import asyncio
import time
from types import SimpleNamespace

from app.mw.chat_delay import ChatDelayMiddleware
from app import storage


def test_chat_delay_throttles(monkeypatch):
    # Setup fake storage responses
    monkeypatch.setattr(storage, "get_last_chat", lambda uid: {"id": 1})
    monkeypatch.setattr(storage, "get_chat", lambda cid: {"min_delay_ms": 1000})

    t = {"val": 10.0}
    monkeypatch.setattr(time, "monotonic", lambda: t["val"])

    calls = []

    async def handler(event, data):
        calls.append(event.text)

    class Message:
        def __init__(self, text="hi"):
            self.text = text
            self.from_user = SimpleNamespace(id=123)
            self.replies = []

        async def answer(self, text):
            self.replies.append(text)

    mw = ChatDelayMiddleware()
    msgs = []

    async def run():
        msg1 = Message()
        await mw(handler, msg1, {})  # first message processed
        t["val"] = 10.5
        msg2 = Message()
        msgs.append(msg2)
        await mw(handler, msg2, {})  # should be throttled
        t["val"] = 11.5
        msg3 = Message()
        await mw(handler, msg3, {})  # processed after delay

    asyncio.run(run())

    assert calls == ["hi", "hi"]
    assert msgs[0].replies  # received warning
