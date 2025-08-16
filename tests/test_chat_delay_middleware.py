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


def test_chat_delay_cleanup(monkeypatch):
    monkeypatch.setattr(storage, "get_last_chat", lambda uid: {"id": uid})
    monkeypatch.setattr(storage, "get_chat", lambda cid: {"min_delay_ms": 1000})

    t = {"val": 0.0}
    monkeypatch.setattr(time, "monotonic", lambda: t["val"])

    async def handler(event, data):
        pass

    class Message:
        def __init__(self, uid: int):
            self.text = "hi"
            self.from_user = SimpleNamespace(id=uid)

        async def answer(self, text):
            pass

    mw = ChatDelayMiddleware()

    async def run():
        # create messages for chats 1..3
        for uid in range(1, 4):
            await mw(handler, Message(uid), {})
            t["val"] += 0.1
        # advance time beyond delay * 2 and send another message
        t["val"] = 3.0
        await mw(handler, Message(4), {})

    asyncio.run(run())

    assert list(mw._last.keys()) == [4]
