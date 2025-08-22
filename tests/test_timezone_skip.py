import asyncio
import asyncio
import sys
import types
from types import SimpleNamespace

# --- Setup helpers ---

def setup_user_module(monkeypatch):
    storage_data = {}

    def set_user_field(uid, field, value):
        storage_data.setdefault(uid, {})[field] = value

    storage_module = types.SimpleNamespace(set_user_field=set_user_field)
    monkeypatch.setitem(sys.modules, "app.storage", storage_module)

    # minimal stubs for other imports
    app_defs = types.SimpleNamespace(APPS={}, COMBOS={})
    monkeypatch.setitem(sys.modules, "app.app_defs", app_defs)

    config_module = types.SimpleNamespace(settings=SimpleNamespace(sub_channel_id=0))
    monkeypatch.setitem(sys.modules, "app.config", config_module)

    tz_module = types.SimpleNamespace(
        tz_keyboard=lambda *a, **k: "KB",
        parse_tz_offset=lambda d: int(d.split(":", 1)[1]),
    )
    monkeypatch.setitem(sys.modules, "app.utils.tz", tz_module)

    telegram_mod = types.ModuleType("app.utils.telegram")
    async def safe_edit_text(message, text, **kwargs):
        message.edited = text
    telegram_mod.safe_edit_text = safe_edit_text
    monkeypatch.setitem(sys.modules, "app.utils.telegram", telegram_mod)

    # minimal aiogram stubs
    aiogram = types.ModuleType("aiogram")

    class _FItem:
        def startswith(self, *args, **kwargs):
            return self

        def __eq__(self, other):
            return self

    class _F:
        data = _FItem()
        text = _FItem()

    class Router:
        def __init__(self, *args, **kwargs):
            pass

        def callback_query(self, *args, **kwargs):
            def wrapper(fn):
                return fn
            return wrapper

        def message(self, *args, **kwargs):
            def wrapper(fn):
                return fn
            return wrapper

    aiogram.Router = Router
    aiogram.F = _F()

    filters_mod = types.ModuleType("aiogram.filters")

    class CommandStart:
        def __init__(self, *args, **kwargs):
            pass

    class CommandObject:
        def __init__(self, *args, **kwargs):
            self.args = ""

    filters_mod.CommandStart = CommandStart
    filters_mod.CommandObject = CommandObject
    monkeypatch.setitem(sys.modules, "aiogram.filters", filters_mod)
    aiogram.filters = filters_mod

    types_mod = types.ModuleType("aiogram.types")
    types_mod.Message = object
    types_mod.ReplyKeyboardMarkup = object
    types_mod.CallbackQuery = object
    monkeypatch.setitem(sys.modules, "aiogram.types", types_mod)
    aiogram.types = types_mod

    class ReplyKeyboardBuilder:
        def __init__(self):
            pass

        def button(self, **kwargs):
            pass

        def adjust(self, *args):
            pass

        def as_markup(self, **kwargs):
            return "KB"

    keyboard_mod = types.ModuleType("aiogram.utils.keyboard")
    keyboard_mod.ReplyKeyboardBuilder = ReplyKeyboardBuilder
    monkeypatch.setitem(sys.modules, "aiogram.utils.keyboard", keyboard_mod)

    utils_mod = types.ModuleType("aiogram.utils")
    utils_mod.keyboard = keyboard_mod
    monkeypatch.setitem(sys.modules, "aiogram.utils", utils_mod)

    monkeypatch.setitem(sys.modules, "aiogram", aiogram)

    import app.handlers.user as user
    monkeypatch.setattr(user, "main_menu_kb", lambda uid: "KB")
    monkeypatch.setattr(user, "storage", storage_module)

    return user, storage_data


def setup_profile_module(monkeypatch):
    storage_data = {}

    def set_user_field(uid, field, value):
        storage_data.setdefault(uid, {})[field] = value

    def get_user(uid):
        return storage_data.get(uid, {})

    storage_module = types.SimpleNamespace(set_user_field=set_user_field, get_user=get_user)
    monkeypatch.setitem(sys.modules, "app.storage", storage_module)

    config_module = types.SimpleNamespace(settings=SimpleNamespace())
    monkeypatch.setitem(sys.modules, "app.config", config_module)

    scheduler_module = types.SimpleNamespace(rebuild_user_jobs=lambda *a, **k: None)
    monkeypatch.setitem(sys.modules, "app.scheduler", scheduler_module)

    tz_module = types.SimpleNamespace(
        tz_keyboard=lambda *a, **k: "KB",
        parse_tz_offset=lambda d: int(d.split(":", 1)[1]),
    )
    monkeypatch.setitem(sys.modules, "app.utils.tz", tz_module)

    telegram_mod = types.ModuleType("app.utils.telegram")
    async def safe_edit_text(message, text, **kwargs):
        message.edited = text
    telegram_mod.safe_edit_text = safe_edit_text
    monkeypatch.setitem(sys.modules, "app.utils.telegram", telegram_mod)

    # aiogram stubs (same as above)
    aiogram = types.ModuleType("aiogram")

    class _FItem:
        def startswith(self, *args, **kwargs):
            return self

        def __eq__(self, other):
            return self

    class _F:
        data = _FItem()

    class Router:
        def __init__(self, *args, **kwargs):
            pass

        def callback_query(self, *args, **kwargs):
            def wrapper(fn):
                return fn
            return wrapper

        def message(self, *args, **kwargs):
            def wrapper(fn):
                return fn
            return wrapper

    aiogram.Router = Router
    aiogram.F = _F()

    filters_mod = types.ModuleType("aiogram.filters")

    class Command:
        def __init__(self, *args, **kwargs):
            pass

    class CommandStart:
        def __init__(self, *args, **kwargs):
            pass

    filters_mod.Command = Command
    filters_mod.CommandStart = CommandStart
    monkeypatch.setitem(sys.modules, "aiogram.filters", filters_mod)
    aiogram.filters = filters_mod

    types_mod = types.ModuleType("aiogram.types")
    types_mod.CallbackQuery = object
    types_mod.Message = object
    monkeypatch.setitem(sys.modules, "aiogram.types", types_mod)
    aiogram.types = types_mod

    keyboard_mod = types.ModuleType("aiogram.utils.keyboard")
    keyboard_mod.InlineKeyboardBuilder = object
    monkeypatch.setitem(sys.modules, "aiogram.utils.keyboard", keyboard_mod)

    utils_mod = types.ModuleType("aiogram.utils")
    utils_mod.keyboard = keyboard_mod
    monkeypatch.setitem(sys.modules, "aiogram.utils", utils_mod)

    monkeypatch.setitem(sys.modules, "aiogram", aiogram)

    # stubs for dependent handlers
    balance_stub = types.ModuleType("app.handlers.balance")
    balance_stub._balance_text = lambda user_id: "balance"
    monkeypatch.setitem(sys.modules, "app.handlers.balance", balance_stub)

    payments_stub = types.ModuleType("app.handlers.payments")
    payments_stub.cmd_pay = lambda msg: None
    monkeypatch.setitem(sys.modules, "app.handlers.payments", payments_stub)

    profile = __import__("app.handlers.profile", fromlist=["*"])
    monkeypatch.setattr(profile, "_profile_text", lambda u: "P")
    monkeypatch.setattr(profile, "_profile_kb", lambda u: "KB")
    monkeypatch.setattr(profile, "storage", storage_module)

    return profile, storage_data


# --- Dummy telegram objects ---

class DummyMessage:
    def __init__(self):
        self.answers = []
        self.edited = None

    async def answer(self, text, reply_markup=None):
        self.answers.append((text, reply_markup))


class DummyCall:
    def __init__(self, data):
        self.data = data
        self.from_user = SimpleNamespace(id=1)
        self.message = DummyMessage()
        self.answered = []

    async def answer(self, text=None, show_alert=False):
        self.answered.append((text, show_alert))


# --- Tests ---

def test_user_timezone_skip(monkeypatch):
    sys.modules.pop("app.handlers.user", None)
    user, storage = setup_user_module(monkeypatch)
    call = DummyCall("tz:skip")
    asyncio.run(user.cb_set_tz(call))
    assert storage[1]["tz_offset_min"] == 0
    sys.modules.pop("app.handlers.user", None)


def test_profile_timezone_skip(monkeypatch):
    sys.modules.pop("app.handlers.profile", None)
    profile, storage = setup_profile_module(monkeypatch)
    call = DummyCall("tzprof:skip")
    asyncio.run(profile.cb_tz_prof(call))
    assert storage[1]["tz_offset_min"] == 0
    sys.modules.pop("app.handlers.profile", None)
