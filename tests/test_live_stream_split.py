import sys
import types

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
async def live_stream(*args, **kwargs):
    if False:
        yield {}
async def summarize_chat(*args, **kwargs):
    pass
domain_chats.chat_turn = chat_turn
domain_chats.live_stream = live_stream
domain_chats.summarize_chat = summarize_chat
sys.modules["app.domain.chats"] = domain_chats

prev_sched = sys.modules.get("app.scheduler")
scheduler = types.ModuleType("app.scheduler")
def schedule_silence_check(*args, **kwargs):
    pass
scheduler.schedule_silence_check = schedule_silence_check
sys.modules["app.scheduler"] = scheduler

from app.handlers.chats import _extract_sections

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
