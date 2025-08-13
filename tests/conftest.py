import sys
import types


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

filters = types.ModuleType("aiogram.filters")
filters.Command = _Dummy

types_mod = types.ModuleType("aiogram.types")
types_mod.Message = _Dummy
types_mod.CallbackQuery = _Dummy

keyboard_mod = types.ModuleType("aiogram.utils.keyboard")
keyboard_mod.InlineKeyboardBuilder = _InlineKeyboardBuilder

utils_mod = types.ModuleType("aiogram.utils")
utils_mod.keyboard = keyboard_mod

sys.modules.setdefault("aiogram", aiogram)
sys.modules.setdefault("aiogram.filters", filters)
sys.modules.setdefault("aiogram.types", types_mod)
sys.modules.setdefault("aiogram.utils", utils_mod)
sys.modules.setdefault("aiogram.utils.keyboard", keyboard_mod)
