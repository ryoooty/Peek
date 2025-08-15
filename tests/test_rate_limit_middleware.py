import asyncio
from types import SimpleNamespace

from app.mw.rate_limit import RateLimitLLM


def test_rate_limit_queue():
    calls = []

    async def handler(event, data):
        calls.append(event.text)

    class Message:
        def __init__(self, text):
            self.text = text
            self.from_user = SimpleNamespace(id=123)
            self.replies = []

        async def answer(self, text):
            self.replies.append(text)

    async def run():
        mw = RateLimitLLM(rate_seconds=0.01)
        msgs = [Message("1"), Message("2"), Message("3")]
        for msg in msgs:
            await mw(handler, msg, {})
        await asyncio.sleep(0.05)
        if mw._worker_task:
            mw._worker_task.cancel()
            try:
                await mw._worker_task
            except asyncio.CancelledError:
                pass
        return msgs

    msgs = asyncio.run(run())

    assert calls == ["1", "2", "3"]
    assert all(not m.replies for m in msgs)
