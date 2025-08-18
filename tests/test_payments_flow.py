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
        self.admin_ids = [2]
        self.boosty_secret = None
        self.donationalerts_secret = None
        self.subs = SimpleNamespace(nightly_toki_bonus={})
        self.pay_requisites = "PAY"


class DummyBot:
    def __init__(self):
        self.sent_docs = []
        self.sent_messages = []

    async def send_document(self, chat_id, file_id, caption=None, reply_markup=None):
        self.sent_docs.append((chat_id, file_id, caption, reply_markup))

    async def send_message(self, chat_id, text, reply_markup=None):
        self.sent_messages.append((chat_id, text, reply_markup))


class DummyMessage:
    def __init__(self, user_id: int, bot: DummyBot | None = None):
        self.from_user = SimpleNamespace(id=user_id)
        self.bot = bot or DummyBot()
        self.sent = []
        self.edited = []
        self.caption = ""

    async def answer(self, text: str, reply_markup=None):
        self.sent.append((text, reply_markup))

    async def edit_text(self, text: str, reply_markup=None):
        self.edited.append((text, reply_markup))

    async def edit_caption(self, caption: str, reply_markup=None):
        self.caption = caption
        self.edited.append((caption, reply_markup))


class DummyCall:
    def __init__(self, user_id: int, data: str = "", bot: DummyBot | None = None):
        self.from_user = SimpleNamespace(id=user_id)
        self.data = data
        self.message = DummyMessage(user_id, bot)
        self.answered = []
        self.bot = self.message.bot

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
    profile = importlib.import_module("app.handlers.profile")
    payments = importlib.import_module("app.handlers.payments")

    async def dummy_safe_edit_text(message, text, **kwargs):
        await message.edit_text(text, **kwargs)

    monkeypatch.setattr(profile, "safe_edit_text", dummy_safe_edit_text)

    return storage, profile, payments


def test_interactive_payment_flow(tmp_path, monkeypatch):
    storage, profile, payments = _setup(monkeypatch)

    storage.init(tmp_path / "db.sqlite")
    storage.ensure_user(1, "alice")

    bot = DummyBot()

    # user opens balance screen
    call_balance = DummyCall(1, bot=bot)
    asyncio.run(profile.cb_balance(call_balance))
    assert call_balance.message.edited
    assert call_balance.message.edited[0][0].startswith("<b>Баланс")

    # user presses the top up button
    call_pay = DummyCall(1, bot=bot)
    asyncio.run(profile.cb_pay(call_pay))
    assert call_pay.message.sent and call_pay.message.sent[0][0] == "Пополнение баланса"

    # user selects a pay option
    call_buy = DummyCall(1, data="buy:1000", bot=bot)
    asyncio.run(payments.cb_buy(call_buy))
    u = storage.get_user(1)
    assert u["paid_tokens"] == 0
    assert call_buy.message.sent and "Загрузите PDF-чек" in call_buy.message.sent[0][0]
    topup = storage.get_active_topup(1)
    assert topup and topup["status"] == "waiting_receipt"

    # user uploads receipt
    doc_msg = DummyMessage(1, bot)
    doc_msg.document = SimpleNamespace(file_id="FILE", mime_type="application/pdf")
    asyncio.run(payments.doc_receipt(doc_msg))
    topup = storage.get_active_topup(1)
    assert topup and topup["status"] == "pending" and topup["receipt_file_id"] == "FILE"
    assert bot.sent_docs

    # admin approves
    admin_call = DummyCall(2, data=f"topup:approve:{topup['id']}", bot=bot)
    asyncio.run(payments.cb_topup(admin_call))
    u = storage.get_user(1)
    assert u["paid_tokens"] == 1000
