import types
import asyncio

from app.handlers import chats as chats_module


class DummyBot:
    async def send_chat_action(self, chat_id, action):
        pass


class DummyMessage:
    def __init__(self, text: str):
        self.text = text
        self.from_user = types.SimpleNamespace(id=1)
        self.chat = types.SimpleNamespace(id=1)
        self.bot = DummyBot()
        self.answers: list[str] = []

    async def answer(self, text: str, reply_markup=None):
        self.answers.append(text)


async def dummy_typing_loop(msg, stop_evt):
    return


def _make_storage(mode: str):
    storage = types.SimpleNamespace()
    storage.last_chat = {"id": 1, "mode": mode}
    storage.get_last_chat = lambda user_id: storage.last_chat
    storage.touch_activity = lambda user_id: None
    storage.add_message = lambda *args, **kwargs: None
    storage.set_user_chatting = lambda *args, **kwargs: None
    return storage


def test_chatting_text_strips_markers_rp(monkeypatch):
    monkeypatch.setattr(chats_module, "_typing_loop", dummy_typing_loop)
    monkeypatch.setattr(chats_module, "storage", _make_storage("rp"))
    monkeypatch.setattr(chats_module, "schedule_silence_check", lambda *a, **k: None)

    captured = {}

    async def fake_chat_turn(user_id, chat_id, text):
        captured["text"] = text
        class R:
            text = "ok"
            usage_in = usage_out = cost_total = 0
            deficit = 0
        return R()

    monkeypatch.setattr(chats_module, "chat_turn", fake_chat_turn)

    msg = DummyMessage("/s/Hello/n/")
    asyncio.run(chats_module.chatting_text(msg))

    assert captured["text"] == "Hello"
    assert "/s/" not in captured["text"]
    assert "/n/" not in captured["text"]


def test_chatting_text_strips_markers_chat(monkeypatch):
    monkeypatch.setattr(chats_module, "_typing_loop", dummy_typing_loop)
    monkeypatch.setattr(chats_module, "storage", _make_storage("chat"))
    monkeypatch.setattr(chats_module, "schedule_silence_check", lambda *a, **k: None)

    captured = {}

    async def fake_chat_stream(user_id, chat_id, text):
        captured["text"] = text
        yield {"kind": "final", "usage_in": "0", "usage_out": "0", "cost_total": "0", "deficit": "0"}

    monkeypatch.setattr(chats_module, "chat_stream", fake_chat_stream)

    msg = DummyMessage("/s/Hello/n/")
    asyncio.run(chats_module.chatting_text(msg))

    assert captured["text"] == "Hello"
    assert "/s/" not in captured["text"]
    assert "/n/" not in captured["text"]
