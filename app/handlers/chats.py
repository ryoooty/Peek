from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
from typing import TYPE_CHECKING

try:  # pragma: no cover - allow running tests without aiogram installed
    from aiogram import Router, F
    from aiogram.enums import ChatAction
    from aiogram.filters import Command
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.state import State, StatesGroup
    from aiogram.types import CallbackQuery, Message
    from aiogram.utils.keyboard import InlineKeyboardBuilder
except Exception:  # pragma: no cover
    import types

    class _DummyFilter:
        def __getattr__(self, name):
            return self

        def __call__(self, *args, **kwargs):
            return self

        def __and__(self, other):  # noqa: D401 - simple passthrough
            return self

        def __invert__(self):
            return self

        def startswith(self, *args, **kwargs):
            return self

    class Router:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass

        def message(self, *args, **kwargs):
            def decorator(fn):
                return fn

            return decorator

        def callback_query(self, *args, **kwargs):
            def decorator(fn):
                return fn

            return decorator

    F = _DummyFilter()

    class ChatAction:  # type: ignore
        TYPING = "typing"

    class Command:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass

    class FSMContext:  # type: ignore
        pass

    class State:  # type: ignore
        pass

    class StatesGroup:  # type: ignore
        pass

    class CallbackQuery:  # type: ignore
        def __init__(self, *args, **kwargs):
            self.from_user = types.SimpleNamespace(id=0)
            self.message = types.SimpleNamespace(chat=types.SimpleNamespace(id=0))

        async def answer(self, *args, **kwargs):
            pass

    class Message:  # type: ignore
        def __init__(self, *args, **kwargs):
            self.from_user = types.SimpleNamespace(id=0)
            self.chat = types.SimpleNamespace(id=0)
            self.bot = types.SimpleNamespace(send_chat_action=lambda *a, **k: None)

        async def answer(self, *args, **kwargs):
            pass

    class InlineKeyboardBuilder:  # type: ignore
        def __init__(self):
            self._buttons = []

        def button(self, text: str, callback_data: str):
            self._buttons.append(types.SimpleNamespace(text=text, callback_data=callback_data))

        def row(self, *buttons):
            pass

        def adjust(self, *sizes):
            pass

        def as_markup(self):
            return None

from app.config import settings
from app.domain.chats import chat_turn, chat_stream, summarize_chat
from app.scheduler import schedule_silence_check
from app.utils.telegram import safe_edit_text

logger = logging.getLogger(__name__)

router = Router(name="chats")

FEATURE_USAGE_MSG = os.getenv("FEATURE_USAGE_MSG") == "1"

# Fallback flush limits when provider does not send section markers or newlines
FALLBACK_FLUSH_SECONDS = 1.0
FALLBACK_FLUSH_CHARS = 200

if TYPE_CHECKING:
    from app import storage as storage_module

storage: "storage_module | None" = None


def _storage() -> "storage_module":
    global storage
    if storage is None:
        from app import storage as storage_module  # type: ignore
        storage = storage_module
    return storage

class ChatSG(StatesGroup):
    chatting = State()
    importing = State()

def _limits_for(user_id: int):
    u = _storage().get_user(user_id) or {}
    sub = (u.get("subscription") or "free").lower()
    limits = getattr(settings.subs, sub, settings.subs.free)
    return limits


def chats_page_kb(user_id: int, page: int):
    lim = _limits_for(user_id)
    rows = _storage().list_user_chats(user_id, page=page, page_size=lim.chats_page_size)
    kb = InlineKeyboardBuilder()
    for r in rows:
        label = f"{r['seq_no']} — {r['char_name']}"
        kb.button(text=label, callback_data=f"chat:open:{r['id']}")
    # пагинация (макс pages_max)
    nav = InlineKeyboardBuilder()
    if page > 1:
        nav.button(text="←", callback_data=f"chats:page:{page-1}")
    nav.button(text=f"{page}/{lim.chats_pages_max}", callback_data="chats:noop")
    if page < lim.chats_pages_max:
        nav.button(text="→", callback_data=f"chats:page:{page+1}")
    kb.row(*nav.buttons)
    kb.adjust(1)
    return kb


async def list_chats(msg_or_call: Message | CallbackQuery, page: int = 1):
    user_id = msg_or_call.from_user.id if isinstance(msg_or_call, CallbackQuery) else msg_or_call.from_user.id
    kb = chats_page_kb(user_id, page)
    text = "Ваши чаты:"
    if isinstance(msg_or_call, CallbackQuery):
        await safe_edit_text(msg_or_call.message, text, callback=msg_or_call, reply_markup=kb.as_markup())
        await msg_or_call.answer()
    else:
        await msg_or_call.answer(text, reply_markup=kb.as_markup())


@router.message(Command("chats"))
async def cmd_chats(msg: Message):
    await list_chats(msg, page=1)


@router.callback_query(F.data.startswith("chats:page:"))
async def cb_chats_page(call: CallbackQuery):
    parts = call.data.split(":")
    if len(parts) < 3 or not parts[2].isdigit():
        return await call.answer("Некорректные данные", show_alert=True)
    page = int(parts[2])
    await list_chats(call, page=page)


def chat_inline_kb(chat_id: int, user_id: int):
    ch = _storage().get_chat(chat_id) or {}
    # 1: Продолжить, Что тут было
    kb = InlineKeyboardBuilder()
    kb.button(text="▶ Продолжить", callback_data=f"chat:cont:{chat_id}")
    kb.button(text="🧠 Что тут было", callback_data=f"chat:what:{chat_id}")
    # 2: В избранное/Персонаж
    is_fav = int(ch.get("is_favorite") or 0) == 1
    kb.button(text=("★ Убрать из избранного" if is_fav else "☆ В избранное"), callback_data=f"chat:fav:{chat_id}")
    kb.button(text=f"🎭 Персонаж", callback_data=f"char:open:{ch['char_id']}")
    # 3: Экспорт/Импорт
    kb.button(text="⬇ Экспорт", callback_data=f"chat:export:{chat_id}")
    kb.button(text="⬆ Импорт", callback_data=f"chat:import:{chat_id}")
    # 4: Меню/Удалить
    kb.button(text="⬅ Назад", callback_data="chars:menu")
    kb.button(text="🗑 Удалить", callback_data=f"chat:del:{chat_id}")
    kb.adjust(2, 2, 2, 2)
    return kb


async def open_chat_inline(msg_or_call: Message | CallbackQuery, *, chat_id: int):
    ch = _storage().get_chat(chat_id)
    if not ch:
        if isinstance(msg_or_call, CallbackQuery):
            return await msg_or_call.answer("Чат не найден", show_alert=True)
        return await msg_or_call.answer("Чат не найден")
    text = f"Чат #{ch['seq_no']} — {ch['char_name']}\nРежим: {ch['mode']}"
    kb = chat_inline_kb(chat_id, ch["user_id"])
    if isinstance(msg_or_call, CallbackQuery):
        await safe_edit_text(msg_or_call.message, text, callback=msg_or_call, reply_markup=kb.as_markup())
        await msg_or_call.answer()
    else:
        await msg_or_call.answer(text, reply_markup=kb.as_markup())


# ---- Inline actions ----
@router.callback_query(F.data.startswith("chat:open:"))
async def cb_open_chat(call: CallbackQuery):
    parts = call.data.split(":")
    if len(parts) < 3 or not parts[2].isdigit():
        return await call.answer("Некорректные данные", show_alert=True)
    chat_id = int(parts[2])
    await open_chat_inline(call, chat_id=chat_id)


@router.callback_query(F.data.startswith("chat:cont:"))
async def cb_continue_chat(call: CallbackQuery):
    await call.answer("Напишите сообщение…")


@router.callback_query(F.data.startswith("chat:what:"))
async def cb_what(call: CallbackQuery):
    parts = call.data.split(":")
    if len(parts) < 3 or not parts[2].isdigit():
        return await call.answer("Некорректные данные", show_alert=True)
    chat_id = int(parts[2])
    try:
        await call.answer("Думаю…")
        await call.message.bot.send_chat_action(call.message.chat.id, ChatAction.TYPING)
        u = _storage().get_user(call.from_user.id) or {}
        model = (u.get("default_model") or settings.default_model)

        s = await summarize_chat(chat_id, model=model)
        await safe_edit_text(
            call.message,
            f"Кратко о чате:\n\n{s.text}",
            callback=call,
            reply_markup=chat_inline_kb(chat_id, call.from_user.id).as_markup(),
        )
    except Exception:
        await call.answer("Не удалось получить краткое содержание", show_alert=True)


@router.callback_query(F.data.startswith("chat:fav:"))
async def cb_fav(call: CallbackQuery):
    parts = call.data.split(":")
    if len(parts) < 3 or not parts[2].isdigit():
        return await call.answer("Некорректные данные", show_alert=True)
    chat_id = int(parts[2])
    lim = _limits_for(call.from_user.id)
    ok = _storage().toggle_fav_chat(call.from_user.id, chat_id, allow_max=lim.fav_chats_max)
    if not ok:
        await call.answer("Лимит избранных чатов исчерпан", show_alert=True)
    await open_chat_inline(call, chat_id=chat_id)


@router.callback_query(F.data.startswith("chat:export:"))
async def cb_export(call: CallbackQuery):
    parts = call.data.split(":")
    if len(parts) < 3 or not parts[2].isdigit():
        return await call.answer("Некорректные данные", show_alert=True)
    chat_id = int(parts[2])
    txt = _storage().export_chat_txt(chat_id)
    await safe_edit_text(
        call.message,
        "Экспорт чата (txt): отправляю файлом…",
        callback=call,
        reply_markup=chat_inline_kb(chat_id, call.from_user.id).as_markup(),
    )
    try:
        from aiogram.types import BufferedInputFile  # type: ignore

        doc = BufferedInputFile(txt.encode("utf-8"), filename=f"chat_{chat_id}.txt")
        await call.message.answer_document(doc)
        await call.answer()
    except Exception:
        logger.exception("Failed to export chat %s", chat_id)
        await call.answer("Не удалось экспортировать чат", show_alert=True)


@router.callback_query(F.data.startswith("chat:import:"))
async def cb_import(call: CallbackQuery, state: FSMContext):
    parts = call.data.split(":")
    if len(parts) < 3 or not parts[2].isdigit():
        return await call.answer("Некорректные данные", show_alert=True)
    chat_id = int(parts[2])
    await state.set_state(ChatSG.importing)
    await state.update_data(chat_id=chat_id)
    await safe_edit_text(
        call.message,
        "Пришлите один файл TXT/DOCX/PDF (до 5 МБ) для пополнения контекста.",
        callback=call,
        reply_markup=chat_inline_kb(chat_id, call.from_user.id).as_markup(),
    )
    await call.answer()


@router.message(ChatSG.importing, F.document)
async def import_doc(msg: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = int(data.get("chat_id") or 0)
    doc = msg.document
    if not doc or int(doc.file_size or 0) > 5_000_000:
        await msg.answer("Файл слишком большой или отсутствует. Отправьте TXT/DOCX/PDF до 5 МБ.")
        return
    ext = (doc.file_name or "").lower()
    try:
        file = await msg.bot.get_file(doc.file_id)
        from io import BytesIO
        buf = BytesIO()
        await msg.bot.download_file(file.file_path, buf)
        buf.seek(0)
        text = ""
        if ext.endswith(".txt"):
            text = buf.read().decode("utf-8", errors="ignore")
        elif ext.endswith(".docx"):
            try:
                from docx import Document  # type: ignore
                d = Document(buf)
                text = "\n".join(p.text for p in d.paragraphs)
            except Exception:
                text = "(docx не поддержан на этом хосте)"
        elif ext.endswith(".pdf"):
            try:
                import fitz  # PyMuPDF  # type: ignore
                docpdf = fitz.open(stream=buf.getvalue(), filetype="pdf")
                text = "\n".join(page.get_text() for page in docpdf)
            except Exception:
                text = "(pdf не поддержан на этом хосте)"
        else:
            text = "(формат не поддержан)"
        if text.strip():
            _storage().add_message(chat_id, is_user=True, content=f"[Импортированный контент]\n{text[:4000]}")
            await msg.answer("Импортировано в контекст.", reply_markup=chat_inline_kb(chat_id, msg.from_user.id).as_markup())
        else:
            await msg.answer("Не удалось извлечь текст из файла.")
    except Exception:
        logger.exception("Import failed", exc_info=True)
        await msg.answer("Ошибка при импорте файла")
    finally:
        await state.clear()


@router.callback_query(F.data.startswith("chat:del:"))
async def cb_del(call: CallbackQuery):
    parts = call.data.split(":")
    if len(parts) < 3 or not parts[2].isdigit():
        return await call.answer("Некорректные данные", show_alert=True)
    chat_id = int(parts[2])
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Да, удалить", callback_data=f"chat:delok:{chat_id}")
    kb.button(text="⬅ Отмена", callback_data=f"chat:open:{chat_id}")
    kb.adjust(2)
    await safe_edit_text(call.message, "Удалить чат? Это действие необратимо.", callback=call, reply_markup=kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("chat:delok:"))
async def cb_delok(call: CallbackQuery):
    parts = call.data.split(":")
    if len(parts) < 3 or not parts[2].isdigit():
        return await call.answer("Некорректные данные", show_alert=True)
    chat_id = int(parts[2])
    if _storage().delete_chat(chat_id, call.from_user.id):
        kb = InlineKeyboardBuilder()
        kb.button(text="⬅ Назад", callback_data="chars:menu")
        kb.adjust(1)
        await safe_edit_text(call.message, "Чат удалён. Вернуться к персонажам:", callback=call, reply_markup=kb.as_markup())
    else:
        await safe_edit_text(
            call.message,
            "Не удалось удалить чат.",
            callback=call,
            reply_markup=chat_inline_kb(chat_id, call.from_user.id).as_markup(),
        )
    await call.answer()


# ------ Сообщения (RP/Chat) ------
async def _typing_loop(msg: Message, stop_evt: asyncio.Event):
    try:
        while not stop_evt.is_set():
            await msg.bot.send_chat_action(msg.chat.id, ChatAction.TYPING)
            await asyncio.sleep(4)
    except Exception:
        logger.exception("Typing loop failed for chat %s", msg.chat.id)


def _extract_sections(buf: str, *, force: bool = False) -> tuple[list[str], str]:
    """Extract marked sections from ``buf``.

    Provider responses may optionally wrap fragments into ``/s/`` ... ``/n/``
    markers.  When markers are missing or delayed we still want to emit
    partial text as soon as a newline arrives.  The function therefore looks
    for the earliest of a marker pair or a newline and returns complete
    fragments while keeping the remainder in ``buf``.  If ``force`` is true
    any remaining buffer is returned as a final fragment.
    """

    parts: list[str] = []
    while buf:
        start = buf.find("/s/")
        newline = buf.find("\n")

        # no start marker before the next newline – flush plain text
        if start == -1 or (0 <= newline < start):
            if newline == -1:
                break
            parts.append(buf[:newline].strip())
            buf = buf[newline + 1 :]
            continue

        # discard plain prefix before the marker
        if start > 0:
            prefix = buf[:start]
            for line in prefix.splitlines():
                if line.strip():
                    parts.append(line.strip())
            buf = buf[start:]

        # buf now starts with '/s/'
        end = buf.find("/n/", 3)
        newline = buf.find("\n", 3)
        if end == -1 and newline == -1:
            break
        if newline != -1 and (end == -1 or newline < end):
            parts.append(buf[3:newline].strip())
            buf = buf[newline + 1 :]
        else:
            parts.append(buf[3:end].strip())
            buf = buf[end + 3 :]

    if force and buf.strip():
        parts.append(buf.strip())
        buf = ""

    return parts, buf


def _fallback_segments(text: str) -> list[str]:
    """Split plain ``text`` into chunks for manual flushing.

    The provider may return a full answer in a single chunk or only in the
    final event.  To preserve the live-mode cadence we split such text into
    reasonably sized fragments, preferring sentence boundaries and falling back
    to ``FALLBACK_FLUSH_CHARS``.
    """

    if len(text) <= FALLBACK_FLUSH_CHARS:
        return [text.strip()]

    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    buf = ""
    for sent in sentences:
        if not sent:
            continue
        candidate = f"{buf} {sent}".strip() if buf else sent.strip()
        if len(candidate) <= FALLBACK_FLUSH_CHARS:
            buf = candidate
            continue
        if buf:
            chunks.append(buf.strip())
        if len(sent) <= FALLBACK_FLUSH_CHARS:
            buf = sent.strip()
        else:
            for i in range(0, len(sent), FALLBACK_FLUSH_CHARS):
                chunks.append(sent[i : i + FALLBACK_FLUSH_CHARS].strip())
            buf = ""
    if buf:
        chunks.append(buf.strip())
    return chunks


@router.message(F.text & ~F.text.startswith("/"))
async def chatting_text(msg: Message):
    # Определяем активный чат (последний «открытый»)
    last = _storage().get_last_chat(msg.from_user.id)
    if not last:
        await msg.answer("Нет активного чата. Откройте персонажа и начните новый чат.")
        return
    chat_id = int(last["id"])
    _storage().touch_activity(msg.from_user.id)
    user_text = re.sub(r"(?<!\w)/(?:s|n)/|/(?:s|n)/(?!\w)", "", msg.text)
    _storage().add_message(chat_id, is_user=True, content=user_text)
    _storage().set_user_chatting(msg.from_user.id, True)  # <-- флаг «диалог начался»
    # Индикатор «печатает…»
    stop = asyncio.Event()
    typer = asyncio.create_task(_typing_loop(msg, stop))

    try:
        mode = (last.get("mode") or "rp").lower()


        if mode == "chat":
            full = ""
            buf = ""
            loop = asyncio.get_running_loop()
            last_flush = loop.time()

            async for ev in chat_stream(msg.from_user.id, chat_id, user_text):
                if ev["kind"] == "chunk":
                    buf += ev["text"]
                    parts, buf = _extract_sections(buf)
                    if parts:
                        last_flush = loop.time()
                    for piece in parts:
                        if piece and piece.strip():
                            await msg.answer(piece)
                            full += (("\n" if full else "") + piece)

                    now = loop.time()
                    if buf and (
                        len(buf) >= FALLBACK_FLUSH_CHARS
                        or now - last_flush >= FALLBACK_FLUSH_SECONDS
                    ):
                        extra, buf = _extract_sections(buf, force=True)
                        if not full and len(extra) == 1 and not buf:
                            # Single big chunk with no markers – keep in buffer
                            buf = extra[0]
                        else:
                            for piece in extra:
                                if piece and piece.strip():
                                    await msg.answer(piece)
                                    full += (("\n" if full else "") + piece)
                            last_flush = now

                elif ev["kind"] == "final":
                    # provider may deliver remaining text either in ``buf`` or
                    # directly within the final event
                    final_text = ev.get("text") or ""
                    if final_text:
                        buf += final_text

                    pieces: list[str] = []
                    if buf:
                        parts, buf = _extract_sections(buf, force=True)
                        # if the whole reply arrived at once (no prior chunks
                        # and a single part), split it manually to imitate
                        # streaming cadence
                        if not full and len(parts) == 1:
                            pieces = _fallback_segments(parts[0])
                        else:
                            pieces = [p for p in parts if p and p.strip()]

                    for idx, piece in enumerate(pieces):
                        await msg.answer(piece)
                        full += (("\n" if full else "") + piece)
                        if len(pieces) > 1 and idx < len(pieces) - 1:
                            await asyncio.sleep(FALLBACK_FLUSH_SECONDS)
                    usage_in = int(ev.get("usage_in") or 0)
                    usage_out = int(ev.get("usage_out") or 0)
                    if int(ev.get("deficit") or 0) > 0:
                        await msg.answer("⚠ Баланс токенов на нуле. Пополните баланс, чтобы продолжить комфортно.")
                    else:
                        _storage().add_message(
                            chat_id,
                            is_user=False,
                            content=full,
                            usage_in=usage_in,
                            usage_out=usage_out,
                        )
                        if FEATURE_USAGE_MSG:
                            await msg.answer(
                                f"usage_in: {usage_in}, usage_out: {usage_out}"
                            )
                                # ответ в live завершён — теперь стартуем таймер «10 минут тишины»

                    schedule_silence_check(msg.from_user.id, chat_id, delay_sec=600)

        else:
            # RP: один ответ

            r = await chat_turn(msg.from_user.id, chat_id, user_text)

            if r.deficit > 0:
                await msg.answer(r.text)
            else:
                _storage().add_message(
                    chat_id,
                    is_user=False,
                    content=r.text,
                    usage_in=r.usage_in,
                    usage_out=r.usage_out,
                )
                await msg.answer(r.text)
                if FEATURE_USAGE_MSG:
                    await msg.answer(
                        f"usage_in: {r.usage_in}, usage_out: {r.usage_out}"
                    )
            schedule_silence_check(msg.from_user.id, chat_id, delay_sec=600)

    finally:
        stop.set()
        try:
            await asyncio.wait_for(typer, timeout=0.1)
        except asyncio.TimeoutError:
            typer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await typer
        _storage().set_user_chatting(msg.from_user.id, False)  # <-- диалог завершился
