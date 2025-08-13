import sys
import types

aiogram = types.ModuleType("aiogram")

class Router:
    def __init__(self, name: str | None = None):
        self.name = name
    def message(self, *args, **kwargs):
        def decorator(func):
            return func
        return decorator
    def callback_query(self, *args, **kwargs):
        def decorator(func):
            return func
        return decorator

class FObj:
    def __getattr__(self, name):
        return self
    def __eq__(self, other):
        return self

F = FObj()

filters = types.ModuleType("filters")

class Command:
    def __init__(self, *args, **kwargs):
        pass

filters.Command = Command

# types submodule
atypes = types.ModuleType("types")

class Message:
    pass

class CallbackQuery:
    pass

atypes.Message = Message
atypes.CallbackQuery = CallbackQuery

input_file = types.ModuleType("input_file")

class FSInputFile:
    pass

input_file.FSInputFile = FSInputFile
atypes.input_file = input_file

# exceptions submodule
exceptions = types.ModuleType("exceptions")

class TelegramBadRequest(Exception):
    pass

exceptions.TelegramBadRequest = TelegramBadRequest

aiogram.Router = Router
aiogram.F = F
aiogram.filters = filters
aiogram.types = atypes
aiogram.exceptions = exceptions

sys.modules.setdefault("aiogram", aiogram)
sys.modules.setdefault("aiogram.filters", filters)
sys.modules.setdefault("aiogram.types", atypes)
sys.modules.setdefault("aiogram.types.input_file", input_file)
sys.modules.setdefault("aiogram.exceptions", exceptions)
