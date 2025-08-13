import sys
import types

aiogram = types.ModuleType('aiogram')

class BaseMiddleware:
    pass

aiogram.BaseMiddleware = BaseMiddleware

# types submodule
aiogram_types = types.ModuleType('aiogram.types')

class TelegramObject:
    pass

class Message(TelegramObject):
    def __init__(self, from_user=None, text=""):
        self.from_user = from_user
        self.text = text
        self.answers = []
    async def answer(self, text, reply_markup=None):
        self.answers.append(text)
        return text

class CallbackQuery(TelegramObject):
    def __init__(self, from_user=None, message=None):
        self.from_user = from_user
        self.message = message
    async def answer(self, *args, **kwargs):
        pass

class InlineKeyboardButton:
    def __init__(self, text, url=None, callback_data=None):
        self.text = text
        self.url = url
        self.callback_data = callback_data

class InlineKeyboardMarkup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard

aiogram_types.TelegramObject = TelegramObject
aiogram_types.Message = Message
aiogram_types.CallbackQuery = CallbackQuery
aiogram_types.InlineKeyboardButton = InlineKeyboardButton
aiogram_types.InlineKeyboardMarkup = InlineKeyboardMarkup

sys.modules.setdefault('aiogram', aiogram)
sys.modules.setdefault('aiogram.types', aiogram_types)
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
