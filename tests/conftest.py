
import sys
import types
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))


class _Dummy:
    def __init__(self, *args, **kwargs):
        pass


class _Router:
    def __init__(self, *args, **kwargs):
        pass

    def message(self, *args, **kwargs):
        def wrapper(fn):
            return fn
        return wrapper

    def callback_query(self, *args, **kwargs):
        def wrapper(fn):
            return fn
        return wrapper


class _F:
    def __getattr__(self, name):
        return self

    def __eq__(self, other):
        return True

    def startswith(self, *args, **kwargs):
        return True

    def __and__(self, other):
        return self

    def __rand__(self, other):
        return self

    def __invert__(self):
        return self


class _InlineKeyboardBuilder:
    def __init__(self, *args, **kwargs):
        pass

    def button(self, *args, **kwargs):
        return self

    def adjust(self, *args, **kwargs):
        return self

    def as_markup(self):
        return None


aiogram = types.ModuleType("aiogram")
aiogram.Router = _Router
aiogram.F = _F()
class _BaseMiddleware:
    pass
aiogram.BaseMiddleware = _BaseMiddleware
aiogram.Bot = _Dummy

filters = types.ModuleType("aiogram.filters")
filters.Command = _Dummy

types_mod = types.ModuleType("aiogram.types")
types_mod.Message = _Dummy
types_mod.CallbackQuery = _Dummy
types_mod.TelegramObject = _Dummy
types_mod.InlineKeyboardMarkup = _Dummy
types_mod.InlineKeyboardButton = _Dummy
types_mod.__path__ = []

keyboard_mod = types.ModuleType("aiogram.utils.keyboard")
keyboard_mod.InlineKeyboardBuilder = _InlineKeyboardBuilder

utils_mod = types.ModuleType("aiogram.utils")
utils_mod.keyboard = keyboard_mod

sys.modules.setdefault("aiogram", aiogram)
sys.modules.setdefault("aiogram.filters", filters)
sys.modules.setdefault("aiogram.types", types_mod)
sys.modules.setdefault("aiogram.utils", utils_mod)
sys.modules.setdefault("aiogram.utils.keyboard", keyboard_mod)
exceptions_mod = types.ModuleType("aiogram.exceptions")
exceptions_mod.TelegramBadRequest = _Dummy
enums_mod = types.ModuleType("aiogram.enums")
enums_mod.ChatAction = _Dummy
sys.modules.setdefault("aiogram.exceptions", exceptions_mod)
sys.modules.setdefault("aiogram.enums", enums_mod)
input_file_mod = types.ModuleType("aiogram.types.input_file")
input_file_mod.FSInputFile = _Dummy
fsm_mod = types.ModuleType("aiogram.fsm")
fsm_mod.__path__ = []
fsm_context_mod = types.ModuleType("aiogram.fsm.context")
fsm_context_mod.FSMContext = _Dummy
fsm_state_mod = types.ModuleType("aiogram.fsm.state")
fsm_state_mod.State = _Dummy
fsm_state_mod.StatesGroup = _Dummy
sys.modules.setdefault("aiogram.types.input_file", input_file_mod)
sys.modules.setdefault("aiogram.fsm", fsm_mod)
sys.modules.setdefault("aiogram.fsm.context", fsm_context_mod)
sys.modules.setdefault("aiogram.fsm.state", fsm_state_mod)
