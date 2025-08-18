import sys
import types
import asyncio
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))


class Tariff:
    def __init__(self, input_per_1k: float = 1.0, output_per_1k: float = 1.0, cache_per_1k: float = 0.5):
        self.input_per_1k = input_per_1k
        self.output_per_1k = output_per_1k
        self.cache_per_1k = cache_per_1k


class DummyLimits:
    auto_compress_default = False


class DummySettings:
    def __init__(self):
        self.default_model = "ghost"
        self.model_tariffs = {"ghost": Tariff()}
        self.limits = DummyLimits()
        self.pay_options = [
            {"tokens": 1000, "price_rub": 1, "emoji": "💰"},
        ]
        self.admin_ids = []
        self.boosty_secret = None
        self.donationalerts_secret = None
        self.subs = SimpleNamespace(nightly_toki_bonus={})


class DummyMessage:
    def __init__(self, user_id: int, text: str = ""):
        self.from_user = SimpleNamespace(id=user_id)
        self.text = text
        self.sent = []
        self.edited = []
        self.bot = SimpleNamespace(send_message=lambda *args, **kwargs: None)

    async def answer(self, text: str, reply_markup=None):
        self.sent.append((text, reply_markup))

    async def edit_text(self, text: str, reply_markup=None):
        self.edited.append((text, reply_markup))


class DummyCall:
    def __init__(self, user_id: int, data: str = ""):
        self.from_user = SimpleNamespace(id=user_id)
        self.data = data
        self.message = DummyMessage(user_id)
        self.answered = []

    async def answer(self, text: str | None = None, *args, **kwargs):
        if text:
            self.answered.append(text)


def _setup(monkeypatch):
    config_module = types.ModuleType("app.config")
    config_module.settings = DummySettings()
    config_module.BASE_DIR = ROOT
    config_module.register_reload_hook = lambda fn: None
    monkeypatch.setitem(sys.modules, "app.config", config_module)

    scheduler_module = types.ModuleType("app.scheduler")
    scheduler_module.rebuild_user_jobs = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "app.scheduler", scheduler_module)

    import importlib
    monkeypatch.delitem(sys.modules, "app.storage", raising=False)
    monkeypatch.delitem(sys.modules, "app.handlers.profile", raising=False)
    monkeypatch.delitem(sys.modules, "app.handlers.payments", raising=False)
    monkeypatch.delitem(sys.modules, "app.handlers.balance", raising=False)

    storage = importlib.import_module("app.storage")

    orig_create = storage.create_topup_pending

    def create_topup_pending(user_id: int, amount: float, provider: str) -> int:
        existing = storage.query(
            "SELECT id FROM topups WHERE user_id=? AND status='pending'", (user_id,)
        )
        if existing:
            return int(existing[0]["id"])
        return orig_create(user_id, amount, provider)

    monkeypatch.setattr(storage, "create_topup_pending", create_topup_pending)

    profile = importlib.import_module("app.handlers.profile")
    payments = importlib.import_module("app.handlers.payments")

    async def dummy_safe_edit_text(message, text, **kwargs):
        await message.edit_text(text, **kwargs)

    monkeypatch.setattr(profile, "safe_edit_text", dummy_safe_edit_text)

    return storage, profile, payments


def test_manual_payment_flow(tmp_path, monkeypatch):
    storage, profile, payments = _setup(monkeypatch)

    storage.init(tmp_path / "db.sqlite")
    storage.ensure_user(1, "alice")

    # user opens balance screen
    call_balance = DummyCall(1)
    asyncio.run(profile.cb_balance(call_balance))
    assert call_balance.message.edited
    assert call_balance.message.edited[0][0].startswith("<b>Баланс")

    # user creates manual topup request
    msg = DummyMessage(1, text="/confirm 1")
    asyncio.run(payments.cmd_confirm(msg))
    assert msg.sent and "Заявка" in msg.sent[0][0]

    # second request should be ignored while first pending
    msg2 = DummyMessage(1, text="/confirm 2")
    asyncio.run(payments.cmd_confirm(msg2))
    pending = storage.query(
        "SELECT COUNT(*) AS c FROM topups WHERE user_id=? AND status='pending'",
        (1,),
    )[0]["c"]
    assert pending == 1

    # user uploads pdf receipt
    pdf_path = tmp_path / "receipt.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")
    assert pdf_path.exists()

    # admin approves request
    tid = storage.query(
        "SELECT id FROM topups WHERE user_id=? AND status='pending'", (1,)
    )[0]["id"]
    ok = storage.approve_topup(tid, admin_id=42)
    assert ok
    u = storage.get_user(1)
    assert u["paid_tokens"] == 1000
