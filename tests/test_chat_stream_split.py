import sys
import types
import pytest
import asyncio

# --- temporary stubs for required modules ---
prev_config = sys.modules.get("app.config")
config_module = types.ModuleType("app.config")
class DummySubsLimits:
    chats_page_size = 10
    chats_pages_max = 2
    chars_page_size = 10
    chars_pages_max = 2
    fav_chats_max = 5
    fav_chars_max = 10
class DummySubs:
    def __init__(self):
        self.free = DummySubsLimits()
config_module.settings = types.SimpleNamespace(subs=DummySubs(), default_model="gpt-4o-mini")
sys.modules["app.config"] = config_module

prev_domain = sys.modules.get("app.domain.chats")
domain_chats = types.ModuleType("app.domain.chats")
async def chat_turn(*args, **kwargs):
    pass
async def chat_stream(*args, **kwargs):
    if False:
        yield {}
async def summarize_chat(*args, **kwargs):
    pass
domain_chats.chat_turn = chat_turn
domain_chats.chat_stream = chat_stream
domain_chats.summarize_chat = summarize_chat
sys.modules["app.domain.chats"] = domain_chats

prev_sched = sys.modules.get("app.scheduler")
scheduler = types.ModuleType("app.scheduler")
def schedule_silence_check(*args, **kwargs):
    pass
scheduler.schedule_silence_check = schedule_silence_check
sys.modules["app.scheduler"] = scheduler

import app.handlers.chats as chats_module
_extract_sections = chats_module._extract_sections
chatting_text = chats_module.chatting_text

# restore modules to avoid leaking to other tests
if prev_config is not None:
    sys.modules["app.config"] = prev_config
else:
    del sys.modules["app.config"]

if prev_domain is not None:
    sys.modules["app.domain.chats"] = prev_domain
else:
    del sys.modules["app.domain.chats"]

if prev_sched is not None:
    sys.modules["app.scheduler"] = prev_sched
else:
    del sys.modules["app.scheduler"]


def test_extract_sections_streaming():
    buf = ""
    pieces = []
    chunks = ["/s/Hel", "lo/n//s/Wor", "ld/n/"]
    for chunk in chunks:
        buf += chunk
        parts, buf = _extract_sections(buf)
        pieces.extend(parts)
    assert pieces == ["Hello", "World"]
    assert buf == ""


def test_chat_stream_single_chunk_split(monkeypatch):
    # prepare dummy message and storage
    class DummyBot:
        async def send_chat_action(self, *args, **kwargs):
            pass

    class DummyMessage:
        def __init__(self):
            self.from_user = types.SimpleNamespace(id=1)
            self.chat = types.SimpleNamespace(id=1)
            self.bot = DummyBot()
            self.text = "hi"
            self.answers: list[str] = []

        async def answer(self, text, **kwargs):
            self.answers.append(text)

    class DummyStorage:
        def get_last_chat(self, user_id):
            return {"id": 1, "mode": "chat"}

        def touch_activity(self, user_id):
            pass

        def add_message(self, *args, **kwargs):
            pass

        def set_user_chatting(self, *args, **kwargs):
            pass

    async def fake_chat_stream(user_id, chat_id, text):
        yield {
            "kind": "chunk",
            "text": (
                "Alpha bravo charlie delta. "
                "Echo foxtrot golf hotel. "
                "India juliet kilo lima."
            ),
        }
        yield {"kind": "final", "usage_in": 0, "usage_out": 0}

    async def fake_typing_loop(msg, stop_evt):
        pass

    monkeypatch.setattr(chats_module, "chat_stream", fake_chat_stream)
    monkeypatch.setattr(chats_module, "storage", DummyStorage())
    monkeypatch.setattr(chats_module, "_typing_loop", fake_typing_loop)
    monkeypatch.setattr(chats_module, "FALLBACK_FLUSH_CHARS", 50)

    async def no_sleep(*args, **kwargs):
        pass

    monkeypatch.setattr(chats_module.asyncio, "sleep", no_sleep)

    msg = DummyMessage()
    asyncio.run(chatting_text(msg))

    assert msg.answers == [
        "Alpha bravo charlie delta.",
        "Echo foxtrot golf hotel. India juliet kilo lima.",
    ]
