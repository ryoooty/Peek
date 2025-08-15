# app/handlers/characters.py
from __future__ import annotations

import asyncio
from pathlib import Path

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InputMediaPhoto
from aiogram.types.input_file import FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app import storage
from app.config import BASE_DIR
from app.utils.telegram import safe_edit_text

router = Router(name="characters")


# ---------- helpers ----------


def _esc(s: str | None) -> str:
    if not s:
        return ""
    return s.replace("<", "&lt;").replace(">", "&gt;")


def _char_card_caption(ch: dict) -> str:
    name = _esc(ch.get("name") or "")
    fandom = _esc(ch.get("fandom") or "—")
    info = _esc(ch.get("info_short") or "")
    return f"<b>{name}</b>\nФандом: <i>{fandom}</i>\n{info}"


def _photo_input_for_char(ch: dict):
    """Return an input for the character's photo.

    Local files are preferred over stored Telegram file IDs to ensure that a
    freshly uploaded photo is used when available.
    """

    p = (ch.get("photo_path") or "").strip()
    if p and Path(p).exists():
        return FSInputFile(p)
    fid = (ch.get("photo_id") or "").strip()
    if fid:
        return fid
    return None


def _char_card_kb(user_id: int, char_id: int) -> InlineKeyboardBuilder:
    has_chats = bool(storage.list_user_chats_by_char(user_id, char_id, limit=1))
    is_fav = storage.is_fav_char(user_id, char_id)

    kb = InlineKeyboardBuilder()
    # 1 строка
    kb.button(text="🆕 Новый чат", callback_data=f"char:new:{char_id}")
    if has_chats:
        kb.button(text="▶ Продолжить", callback_data=f"char:cont:{char_id}")
    # 2 строка
    kb.button(
        text=("★ Убрать из избранного" if is_fav else "☆ В избранное"),
        callback_data=f"char:fav:{char_id}",
    )
    kb.button(text="💬 Мои чаты", callback_data=f"char:chats:{char_id}")
    # 3 строка
    kb.button(text="⬅ Назад", callback_data="chars:menu")
    kb.button(text="⚙ Настройки", callback_data=f"char:settings:{char_id}")
    kb.adjust(2)
    return kb


async def _edit_or_send_card(
    message_or_call, *, media, caption: str, kb: InlineKeyboardBuilder
):
    """
    media: FSInputFile | str | None
    caption — HTML
    """
    m = (
        message_or_call.message
        if isinstance(message_or_call, CallbackQuery)
        else message_or_call
    )

    if media:
        # Если было фото — пробуем заменить media
        if isinstance(message_or_call, CallbackQuery) and getattr(m, "photo", None):
            try:
                await m.edit_media(
                    InputMediaPhoto(type="photo", media=media, caption=caption),
                    reply_markup=kb.as_markup(),
                )
                return
            except Exception:
                # если не получилось отредактировать — пришлём новое сообщение с фото
                pass
        await m.answer_photo(photo=media, caption=caption, reply_markup=kb.as_markup())
    else:
        if isinstance(message_or_call, CallbackQuery):
            await safe_edit_text(m, caption, reply_markup=kb.as_markup())
        else:
            await m.answer(caption, reply_markup=kb.as_markup())


# ---------- open card ----------


async def open_character_card(
    message_or_call: Message | CallbackQuery,
    *,
    char_id: int,
    as_new_message: bool = False,
):
    user_id = message_or_call.from_user.id
    ch = storage.get_character(char_id)
    if not ch:
        if isinstance(message_or_call, CallbackQuery):
            return await message_or_call.answer("Персонаж не найден", show_alert=True)
        return await message_or_call.answer("Персонаж не найден")
    if not (ch.get("photo_path") or "").strip():
        slug = (ch.get("slug") or "").strip()
        if slug:
            media_dir = Path(BASE_DIR) / "media" / "characters"
            for ext in ("jpg", "png"):
                fp = media_dir / f"{slug}.{ext}"
                if fp.exists():
                    storage.set_character_photo_path(char_id, fp.as_posix())
                    ch["photo_path"] = fp.as_posix()
                    break

    kb = _char_card_kb(user_id, char_id)
    caption = _char_card_caption(ch)
    media = _photo_input_for_char(ch)

    # as_new_message зарезервирован на будущее; сейчас поведение идентичное (редактируем, если можем)
    await _edit_or_send_card(message_or_call, media=media, caption=caption, kb=kb)
    if isinstance(message_or_call, CallbackQuery):
        await message_or_call.answer()


# ---------- раздел «персонажи» ----------


@router.message(Command("characters"))
async def characters_menu(msg: Message):
    await show_characters_page(msg, page=1)


def _chars_page_kb(user_id: int, page: int):
    from app.config import settings

    u = storage.get_user(user_id) or {}
    sub = (u.get("subscription") or "free").lower()
    limits = getattr(settings.subs, sub, settings.subs.free)
    rows = storage.list_characters_for_user(
        user_id, page=page, page_size=limits.chars_page_size
    )

    kb = InlineKeyboardBuilder()
    for row in rows:
        mark = "★ " if int(row.get("is_fav") or 0) else ""
        # В тексте кнопки HTML не парсится — экранировать не обязательно
        kb.button(text=f"{mark}{row['name']}", callback_data=f"char:open:{row['id']}")

    # пагинация снизу (макс pages_max)
    nav = InlineKeyboardBuilder()
    if page > 1:
        nav.button(text="←", callback_data=f"chars:page:{page-1}")
    nav.button(text=f"{page}/{limits.chars_pages_max}", callback_data="chars:noop")
    if page < limits.chars_pages_max:
        nav.button(text="→", callback_data=f"chars:page:{page+1}")

    kb.row(*nav.buttons)
    kb.adjust(1)
    return kb


async def show_characters_page(msg_or_call: Message | CallbackQuery, page: int):
    user_id = msg_or_call.from_user.id
    kb = _chars_page_kb(user_id, page)
    text = "Выберите персонажа:"
    if isinstance(msg_or_call, CallbackQuery):
        await safe_edit_text(msg_or_call.message, text, reply_markup=kb.as_markup())
        await msg_or_call.answer()
    else:
        await msg_or_call.answer(text, reply_markup=kb.as_markup())


# ---------- callbacks ----------


@router.callback_query(F.data == "chars:menu")
async def cb_chars_menu(call: CallbackQuery):
    await show_characters_page(call, page=1)


@router.callback_query(F.data.startswith("chars:page:"))
async def cb_chars_page(call: CallbackQuery):
    parts = call.data.split(":")
    if len(parts) < 3 or not parts[2].isdigit():
        return await call.answer("Некорректные данные", show_alert=True)
    page = int(parts[2])
    await show_characters_page(call, page=page)


@router.callback_query(F.data.startswith("char:open:"))
async def cb_open_char(call: CallbackQuery):
    parts = call.data.split(":")
    if len(parts) < 3 or not parts[2].isdigit():
        return await call.answer("Некорректные данные", show_alert=True)
    char_id = int(parts[2])
    await open_character_card(call, char_id=char_id)


@router.callback_query(F.data.startswith("char:fav:"))
async def cb_char_fav(call: CallbackQuery):
    from app.config import settings

    parts = call.data.split(":")
    if len(parts) < 3 or not parts[2].isdigit():
        return await call.answer("Некорректные данные", show_alert=True)
    char_id = int(parts[2])
    u = storage.get_user(call.from_user.id) or {}
    sub = (u.get("subscription") or "free").lower()
    limits = getattr(settings.subs, sub, settings.subs.free)

    ok = storage.toggle_fav_char(
        call.from_user.id, char_id, allow_max=limits.fav_chars_max
    )
    if not ok and not storage.is_fav_char(call.from_user.id, char_id):
        await call.answer("Достигнут лимит избранных персонажей", show_alert=True)

    await open_character_card(call, char_id=char_id)


@router.callback_query(F.data.startswith("char:new:"))
async def cb_char_new(call: CallbackQuery):
    parts = call.data.split(":")
    if len(parts) < 3 or not parts[2].isdigit():
        return await call.answer("Некорректные данные", show_alert=True)
    char_id = int(parts[2])
    await call.answer("Создаю чат…")
    chat_id = storage.create_chat(call.from_user.id, char_id)
    from app.handlers.chats import open_chat_inline

    asyncio.create_task(open_chat_inline(call, chat_id=chat_id))



@router.callback_query(F.data.startswith("char:cont:"))
async def cb_char_cont(call: CallbackQuery):
    parts = call.data.split(":")
    if len(parts) < 3 or not parts[2].isdigit():
        return await call.answer("Некорректные данные", show_alert=True)
    char_id = int(parts[2])
    rows = storage.list_user_chats_by_char(call.from_user.id, char_id, limit=1)
    if not rows:
        await call.answer("Нет чатов с персонажем", show_alert=True)
        return
    from app.handlers.chats import open_chat_inline

    await open_chat_inline(call, chat_id=int(rows[0]["id"]))


@router.callback_query(F.data.startswith("char:chats:"))
async def cb_char_chats(call: CallbackQuery):
    parts = call.data.split(":")
    if len(parts) < 3 or not parts[2].isdigit():
        return await call.answer("Некорректные данные", show_alert=True)
    char_id = int(parts[2])
    rows = storage.list_user_chats_by_char(call.from_user.id, char_id, limit=10)
    if not rows:
        await call.answer("Чатов пока нет.", show_alert=True)
        return await open_character_card(call, char_id=char_id)

    kb = InlineKeyboardBuilder()
    for r in rows:
        kb.button(
            text=f"{r['seq_no']} — {r['char_name']}",
            callback_data=f"chat:open:{r['id']}",
        )
    kb.button(text="⬅ Назад", callback_data=f"char:open:{char_id}")
    kb.adjust(1)

    ch = storage.get_character(char_id)
    title = _esc(ch["name"]) if ch else "персонажем"
    await safe_edit_text(call.message, f"Чаты с {title}:", reply_markup=kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("char:settings:"))
async def cb_char_settings(call: CallbackQuery):
    parts = call.data.split(":")
    if len(parts) < 3 or not parts[2].isdigit():
        return await call.answer("Некорректные данные", show_alert=True)
    char_id = int(parts[2])
    ch = storage.get_character(char_id)
    if not ch:
        return await call.answer("Персонаж не найден", show_alert=True)

    rows = storage.query(
        """
        SELECT COUNT(*) AS c
          FROM messages m
          JOIN chats c ON c.id=m.chat_id
         WHERE c.user_id=? AND c.char_id=?
        """,
        (call.from_user.id, char_id),
    )
    r = rows[0] if rows else None
    cnt = int(r["c"] or 0)


    kb = InlineKeyboardBuilder()
    kb.button(
        text=f"📊 Сообщений с { _esc(ch['name']) }: {cnt}", callback_data="char:noop"
    )
    # «Убрать персонажа из сохранённых» — это «снять из избранного»
    if storage.is_fav_char(call.from_user.id, char_id):
        kb.button(text="🗑 Убрать из избранных", callback_data=f"char:fav:{char_id}")
    kb.button(text="⬅ Назад", callback_data=f"char:open:{char_id}")
    kb.adjust(1)

    await safe_edit_text(call.message, _char_card_caption(ch), reply_markup=kb.as_markup())
    await call.answer()
