import sys
import types

# ---- Stub aiogram and related submodules ----
aiogram = types.ModuleType("aiogram")

class DummyFilter:
    def __getattr__(self, name):
        return self
    def __call__(self, *args, **kwargs):
        return self
    def startswith(self, *args, **kwargs):
        return self
    def __invert__(self):
        return self
    def __and__(self, other):
        return self
    def __or__(self, other):
        return self

class Router:
    def __init__(self, name=None):
        self.name = name
    def message(self, *args, **kwargs):
        def deco(fn):
            return fn
        return deco
    def callback_query(self, *args, **kwargs):
        def deco(fn):
            return fn
        return deco

aiogram.Router = Router
aiogram.F = DummyFilter()
sys.modules.setdefault("aiogram", aiogram)

# enums
enums = types.ModuleType("aiogram.enums")
class ChatAction:
    TYPING = "typing"
enums.ChatAction = ChatAction
sys.modules.setdefault("aiogram.enums", enums)

# filters
filters = types.ModuleType("aiogram.filters")
class Command:
    def __init__(self, *args, **kwargs):
        pass
filters.Command = Command
sys.modules.setdefault("aiogram.filters", filters)

# fsm.context
fsm_context = types.ModuleType("aiogram.fsm.context")
class FSMContext:
    pass
fsm_context.FSMContext = FSMContext
sys.modules.setdefault("aiogram.fsm.context", fsm_context)

# fsm.state
fsm_state = types.ModuleType("aiogram.fsm.state")
class State:
    pass
class StatesGroup:
    pass
fsm_state.State = State
fsm_state.StatesGroup = StatesGroup
sys.modules.setdefault("aiogram.fsm.state", fsm_state)

# types
atypes = types.ModuleType("aiogram.types")
class Message:
    pass
class CallbackQuery:
    pass
atypes.Message = Message
atypes.CallbackQuery = CallbackQuery
sys.modules.setdefault("aiogram.types", atypes)

# utils.keyboard
keyboard = types.ModuleType("aiogram.utils.keyboard")
class InlineKeyboardBuilder:
    def __init__(self, *args, **kwargs):
        pass
    def button(self, *args, **kwargs):
        pass
    def row(self, *args, **kwargs):
        pass
    def adjust(self, *args, **kwargs):
        pass
    def as_markup(self):
        return None
keyboard.InlineKeyboardBuilder = InlineKeyboardBuilder
sys.modules.setdefault("aiogram.utils.keyboard", keyboard)

# (app.config and other modules are stubbed within individual tests as needed)
