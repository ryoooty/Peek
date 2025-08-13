from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from app import storage
from app.config import settings
from app.utils.tz import tz_keyboard

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


async def _check_subscription(msg: Message) -> bool:
    channel_id = settings.sub_channel_id
    if not channel_id:
        return True
    try:
        m = await msg.bot.get_chat_member(chat_id=channel_id, user_id=msg.from_user.id)
        status = getattr(m, "status", "left")
        ok = status in ("member", "administrator", "creator")
    except Exception:
        ok = True
    if ok:
        return True
    url = None
    if settings.sub_channel_username:
        url = f"https://t.me/{settings.sub_channel_username.lstrip('@')}"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📣 Открыть канал", url=url or "https://t.me")],
            [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="gate:check")],
        ]
    )
    await msg.answer("Подпишитесь на канал, чтобы продолжить.", reply_markup=kb)
    return False


@router.message(CommandStart(deep_link=True))
async def start_deeplink(msg: Message, command: CommandObject | None = None):
    storage.ensure_user(msg.from_user.id, msg.from_user.username or None)
    if not await _check_subscription(msg):
        return
    u = storage.get_user(msg.from_user.id) or {}
    if u.get("tz_offset_min") is None:
        await msg.answer("Выберите свой часовой пояс:", reply_markup=tz_keyboard("tzstart"))
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
    storage.ensure_user(msg.from_user.id, msg.from_user.username or None)
    if not await _check_subscription(msg):
        return
    u = storage.get_user(msg.from_user.id) or {}
    if u.get("tz_offset_min") is None:
        await msg.answer("Выберите свой часовой пояс:", reply_markup=tz_keyboard("tzstart"))
        return
    await msg.answer("Здравствуйте!", reply_markup=main_menu_kb(msg.from_user.id))


@router.callback_query(F.data.startswith("tzstart:"))
async def cb_tz_start(call: CallbackQuery):
    try:
        offset = int(call.data.split(":", 1)[1])
    except Exception:
        await call.answer("Некорректное значение", show_alert=True)
        return
    storage.set_user_field(call.from_user.id, "tz_offset_min", offset)
    await call.answer("Часовой пояс установлен")
    await call.message.edit_text(
        f"Часовой пояс установлен: UTC{offset // 60:+d}"
    )
    await call.message.answer(
        "Здравствуйте!", reply_markup=main_menu_kb(call.from_user.id)
    )


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
    from app.handlers.profile import cb_balance

    class FakeCall:
        from_user = msg.from_user
        message = msg

    await cb_balance(FakeCall())  # переиспользуем коллбек
