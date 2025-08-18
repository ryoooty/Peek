import sys
import types
import asyncio
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))


class DummySettings:
    def __init__(self):
        self.admin_ids = [42]
        self.subs = SimpleNamespace(nightly_toki_bonus={})
        self.boosty_secret = None
        self.donationalerts_secret = None


def _setup():
    config_module = types.ModuleType("app.config")
    config_module.settings = DummySettings()
    config_module.BASE_DIR = ROOT
    config_module.register_reload_hook = lambda fn: None
    sys.modules["app.config"] = config_module

    sys.modules.pop("app.storage", None)
    sys.modules.pop("app.handlers.payments", None)

    import importlib
    storage = importlib.import_module("app.storage")
    payments = importlib.import_module("app.handlers.payments")

    return storage, payments


class DummyBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, uid, text):
        self.sent.append(("msg", uid, text))

    async def send_document(self, uid, file_id, caption=None):
        self.sent.append(("doc", uid, file_id, caption))


class DummyMessage:
    def __init__(self, caption, document=None, user_id=1):
        self.caption = caption
        self.text = None
        self.document = document
        self.from_user = SimpleNamespace(id=user_id)
        self.bot = DummyBot()
        self.sent = []

    async def answer(self, text):
        self.sent.append(text)


def test_confirm_receipt_validation(tmp_path):
    storage, payments = _setup()
    storage.init(tmp_path / "db.sqlite")
    storage.ensure_user(1, "alice")

    doc_ok = SimpleNamespace(file_id="f1", mime_type="application/pdf", file_size=1024)
    msg_ok = DummyMessage("/confirm 10", document=doc_ok)
    asyncio.run(payments.cmd_confirm(msg_ok))
    assert any(t[0] == "doc" for t in msg_ok.bot.sent)

    doc_bad = SimpleNamespace(file_id="f2", mime_type="text/plain", file_size=1024)
    msg_bad = DummyMessage("/confirm 5", document=doc_bad)
    asyncio.run(payments.cmd_confirm(msg_bad))
    assert all(t[0] != "doc" for t in msg_bad.bot.sent)
    assert msg_bad.sent

    doc_big = SimpleNamespace(file_id="f3", mime_type="application/pdf", file_size=6_000_000)
    msg_big = DummyMessage("/confirm 7", document=doc_big)
    asyncio.run(payments.cmd_confirm(msg_big))
    assert all(t[0] != "doc" for t in msg_big.bot.sent)
    assert msg_big.sent

    # cleanup modules to avoid cross-test interference
    sys.modules.pop("app.config", None)
    sys.modules.pop("app.storage", None)
    sys.modules.pop("app.handlers.payments", None)
