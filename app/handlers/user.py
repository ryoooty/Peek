from __future__ import annotations

from aiogram import Router, F

from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton

from aiogram.utils.keyboard import ReplyKeyboardBuilder

from app import storage
from app.config import settings


router = Router(name="user")


def main_menu_kb(user_id: int) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    # Первая кнопка: Продолжить (последний чат)
    kb.button(text="▶ Продолжить")
    # Остальные по две в ряд
    kb.button(text="🎭 Персонажи")
    kb.button(text="💬 Мои чаты")
    kb.button(text="👤 Профиль")
    kb.button(text="💰 Баланс")
    kb.adjust(1, 2, 2)
    return kb.as_markup(resize_keyboard=True)



def _gate_kb() -> InlineKeyboardMarkup:
    url = None
    if settings.sub_channel_username:
        url = f"https://t.me/{settings.sub_channel_username.lstrip('@')}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📣 Открыть канал", url=url or "https://t.me")],
        [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="gate:check")],
    ])


async def _check_subscription(msg: Message) -> bool:
    if not settings.sub_channel_id:
        return True
    try:
        member = await msg.bot.get_chat_member(chat_id=settings.sub_channel_id, user_id=msg.from_user.id)
        status = getattr(member, "status", "left")
        return status in ("member", "administrator", "creator")
    except Exception:
        return True



@router.message(CommandStart(deep_link=True))
async def start_deeplink(msg: Message, command: CommandObject | None = None):

    storage.ensure_user(msg.from_user.id, msg.from_user.username or None, default_tz_min=180)
    if not await _check_subscription(msg):
        await msg.answer("Подпишитесь на канал, чтобы продолжить.", reply_markup=_gate_kb())

        return
    payload = (command.args or "").strip() if command else ""
    if payload.startswith("char_"):
        try:
            char_id = int(payload.split("_", 1)[1])
        except Exception:
            char_id = 0
        if char_id:
            from app.handlers.characters import open_character_card
            await open_character_card(msg, char_id=char_id, as_new_message=True)
            return
    await msg.answer("Добро пожаловать!", reply_markup=main_menu_kb(msg.from_user.id))


@router.message(CommandStart())
async def start_plain(msg: Message):

    storage.ensure_user(msg.from_user.id, msg.from_user.username or None, default_tz_min=180)
    if not await _check_subscription(msg):
        await msg.answer("Подпишитесь на канал, чтобы продолжить.", reply_markup=_gate_kb())
        return
    await msg.answer("Здравствуйте!", reply_markup=main_menu_kb(msg.from_user.id))



@router.message(F.text == "▶ Продолжить")
async def continue_last(msg: Message):
    last = storage.get_last_chat(msg.from_user.id)
    if not last:
        await msg.answer("Пока нет активных чатов. Откройте «Персонажи», чтобы начать.")
        return
    from app.handlers.chats import open_chat_inline
    await open_chat_inline(msg, chat_id=int(last["id"]))


@router.message(F.text == "🎭 Персонажи")
async def to_characters(msg: Message):
    from app.handlers.characters import characters_menu
    await characters_menu(msg)


@router.message(F.text == "💬 Мои чаты")
async def to_chats(msg: Message):
    from app.handlers.chats import list_chats
    await list_chats(msg, page=1)


@router.message(F.text == "👤 Профиль")
async def to_profile(msg: Message):
    from app.handlers.profile import show_profile
    await show_profile(msg)


@router.message(F.text == "💰 Баланс")
async def to_balance(msg: Message):
    from app.handlers.balance import cmd_balance

    # Use the balance handler's command directly instead of
    # constructing a fake callback query object.
    await cmd_balance(msg)
