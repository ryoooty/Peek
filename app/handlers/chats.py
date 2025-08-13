from __future__ import annotations

import asyncio
import re

from aiogram import Router, F
from aiogram.enums import ChatAction
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app import storage
from app.config import settings
from app.domain.chats import chat_turn, live_stream, summarize_chat
from app.scheduler import schedule_silence_check

router = Router(name="chats")


class ChatSG(StatesGroup):
    chatting = State()
    importing = State()


_SENT_SPLIT_RE = re.compile(r"(?<=[\.\!\?…])\s+")


def _limits_for(user_id: int):
    u = storage.get_user(user_id) or {}
    sub = (u.get("subscription") or "free").lower()
    limits = getattr(settings.subs, sub, settings.subs.free)
    return limits


def chats_page_kb(user_id: int, page: int):
    lim = _limits_for(user_id)
    rows = storage.list_user_chats(user_id, page=page, page_size=lim.chats_page_size)
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
        await msg_or_call.message.edit_text(text, reply_markup=kb.as_markup())
        await msg_or_call.answer()
    else:
        await msg_or_call.answer(text, reply_markup=kb.as_markup())


@router.message(Command("chats"))
async def cmd_chats(msg: Message):
    await list_chats(msg, page=1)


@router.callback_query(F.data.startswith("chats:page:"))
async def cb_chats_page(call: CallbackQuery):
    page = int(call.data.split(":")[2])
    await list_chats(call, page=page)


def chat_inline_kb(chat_id: int, user_id: int):
    ch = storage.get_chat(chat_id) or {}
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
    kb.button(text="📋 Меню", callback_data="chars:menu")
    kb.button(text="🗑 Удалить", callback_data=f"chat:del:{chat_id}")
    kb.adjust(2, 2, 2, 2)
    return kb


async def open_chat_inline(msg_or_call: Message | CallbackQuery, *, chat_id: int):
    ch = storage.get_chat(chat_id)
    if not ch:
        if isinstance(msg_or_call, CallbackQuery):
            return await msg_or_call.answer("Чат не найден", show_alert=True)
        return await msg_or_call.answer("Чат не найден")
    text = f"Чат #{ch['seq_no']} — {ch['char_name']}\nРежим: {ch['mode']}"
    kb = chat_inline_kb(chat_id, ch["user_id"])
    if isinstance(msg_or_call, CallbackQuery):
        await msg_or_call.message.edit_text(text, reply_markup=kb.as_markup())
        await msg_or_call.answer()
    else:
        await msg_or_call.answer(text, reply_markup=kb.as_markup())


# ---- Inline actions ----
@router.callback_query(F.data.startswith("chat:open:"))
async def cb_open_chat(call: CallbackQuery):
    chat_id = int(call.data.split(":")[2])
    await open_chat_inline(call, chat_id=chat_id)


@router.callback_query(F.data.startswith("chat:cont:"))
async def cb_continue_chat(call: CallbackQuery):
    await call.answer("Напишите сообщение…")


@router.callback_query(F.data.startswith("chat:what:"))
async def cb_what(call: CallbackQuery):
    chat_id = int(call.data.split(":")[2])
    try:
        await call.answer("Думаю…")
        await call.message.bot.send_chat_action(call.message.chat.id, ChatAction.TYPING)
        u = storage.get_user(call.from_user.id) or {}
        model = (u.get("default_model") or settings.default_model)
        s = await summarize_chat(chat_id, model=model)
        await call.message.edit_text(f"Кратко о чате:\n\n{s}", reply_markup=chat_inline_kb(chat_id, call.from_user.id).as_markup())
    except Exception:
        await call.answer("Не удалось получить краткое содержание", show_alert=True)


@router.callback_query(F.data.startswith("chat:fav:"))
async def cb_fav(call: CallbackQuery):
    chat_id = int(call.data.split(":")[2])
    lim = _limits_for(call.from_user.id)
    ok = storage.toggle_fav_chat(call.from_user.id, chat_id, allow_max=lim.fav_chats_max)
    if not ok:
        await call.answer("Лимит избранных чатов исчерпан", show_alert=True)
    await open_chat_inline(call, chat_id=chat_id)


@router.callback_query(F.data.startswith("chat:export:"))
async def cb_export(call: CallbackQuery):
    chat_id = int(call.data.split(":")[2])
    txt = storage.export_chat_txt(chat_id)
    await call.message.edit_text("Экспорт чата (txt): отправляю файлом…", reply_markup=chat_inline_kb(chat_id, call.from_user.id).as_markup())
    try:
        from io import BytesIO
        bio = BytesIO(txt.encode("utf-8"))
        bio.name = f"chat_{chat_id}.txt"
        await call.message.answer_document(bio)
    except Exception:
        pass


@router.callback_query(F.data.startswith("chat:import:"))
async def cb_import(call: CallbackQuery, state: FSMContext):
    chat_id = int(call.data.split(":")[2])
    await state.set_state(ChatSG.importing)
    await state.update_data(chat_id=chat_id)
    await call.message.edit_text("Пришлите один файл TXT/DOCX/PDF (до 5 МБ) для пополнения контекста.", reply_markup=chat_inline_kb(chat_id, call.from_user.id).as_markup())
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
            storage.add_message(chat_id, is_user=True, content=f"[Импортированный контент]\n{text[:4000]}")
            await msg.answer("Импортировано в контекст.", reply_markup=chat_inline_kb(chat_id, msg.from_user.id).as_markup())
        else:
            await msg.answer("Не удалось извлечь текст из файла.")
    except Exception:
        await msg.answer("Ошибка при импорте.")
    finally:
        await state.clear()


@router.callback_query(F.data.startswith("chat:del:"))
async def cb_del(call: CallbackQuery):
    chat_id = int(call.data.split(":")[2])
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Да, удалить", callback_data=f"chat:delok:{chat_id}")
    kb.button(text="⬅ Отмена", callback_data=f"chat:open:{chat_id}")
    kb.adjust(2)
    await call.message.edit_text("Удалить чат? Это действие необратимо.", reply_markup=kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("chat:delok:"))
async def cb_delok(call: CallbackQuery):
    chat_id = int(call.data.split(":")[2])
    if storage.delete_chat(chat_id, call.from_user.id):
        kb = InlineKeyboardBuilder()
        kb.button(text="📋 Меню", callback_data="chars:menu")
        kb.adjust(1)
        await call.message.edit_text("Чат удалён. Вернуться к персонажам:", reply_markup=kb.as_markup())
    else:
        await call.message.edit_text("Не удалось удалить чат.", reply_markup=chat_inline_kb(chat_id, call.from_user.id).as_markup())
    await call.answer()


# ------ Сообщения (RP/Live) ------
async def _typing_loop(msg: Message, stop_evt: asyncio.Event):
    try:
        while not stop_evt.is_set():
            await msg.bot.send_chat_action(msg.chat.id, ChatAction.TYPING)
            await asyncio.sleep(4)
    except Exception:
        pass


def _try_slice(buf: str, *, min_first: int, max_chars: int) -> tuple[str | None, str]:
    # 1) абзац
    if "\n\n" in buf:
        head, tail = buf.split("\n\n", 1)
        return head.strip(), tail.lstrip()
    # 2) конец предложения
    m = list(_SENT_SPLIT_RE.finditer(buf))
    if m and (len(buf) >= min_first):
        pos = m[-1].end()
        return buf[:pos].strip(), buf[pos:].lstrip()
    # 3) защита от слишком длинного
    if len(buf) >= max_chars:
        return buf[:max_chars].rstrip(), buf[max_chars:].lstrip()
    return None, buf


@router.message(F.text & ~F.text.startswith("/"))
async def chatting_text(msg: Message):
    # Определяем активный чат (последний «открытый»)
    last = storage.get_last_chat(msg.from_user.id)
    if not last:
        await msg.answer("Нет активного чата. Откройте персонажа и начните новый чат.")
        return
    chat_id = int(last["id"])
    storage.touch_activity(msg.from_user.id)
    storage.add_message(chat_id, is_user=True, content=msg.text)
    storage.set_user_chatting(msg.from_user.id, True)  # <-- флаг «диалог начался»
    # Индикатор «печатает…»
    stop = asyncio.Event()
    typer = asyncio.create_task(_typing_loop(msg, stop))

    try:
        mode = (last.get("mode") or "rp").lower()

        if mode == "live":
            full = ""
            buf = ""
            min_first = 120
            max_chars = 800

            async for ev in live_stream(msg.from_user.id, chat_id, msg.text):
                if ev["kind"] == "chunk":
                    buf += ev["text"]
                    piece, buf = _try_slice(buf, min_first=min_first, max_chars=max_chars)
                    if piece and piece.strip():
                        await msg.answer(piece)
                        full += (("\n" if full else "") + piece)
                elif ev["kind"] == "final":
                    if buf.strip():
                        await msg.answer(buf.strip())
                        full += (("\n" if full else "") + buf.strip())
                    usage_in = int(ev.get("usage_in") or 0)
                    usage_out = int(ev.get("usage_out") or 0)
                    cost_total = float(ev.get("cost_total") or 0)
                    storage.add_message(
                        chat_id,
                        is_user=False,
                        content=full,
                        usage_in=usage_in,
                        usage_out=usage_out,
                        usage_cost_rub=cost_total,
                    )
                    if int(ev.get("deficit") or 0) > 0:
                        await msg.answer("⚠ Баланс токенов на нуле. Пополните баланс, чтобы продолжить комфортно.")
                                # ответ в live завершён — теперь стартуем таймер «10 минут тишины»
                    schedule_silence_check(msg.from_user.id, chat_id, delay_sec=600)
        else:
            # RP: один ответ
            r = await chat_turn(msg.from_user.id, chat_id, msg.text)
            storage.add_message(
                chat_id,
                is_user=False,
                content=r.text,
                usage_in=r.usage_in,
                usage_out=r.usage_out,
                usage_cost_rub=r.cost_total,
            )
            await msg.answer(r.text)
            if r.deficit > 0:
                await msg.answer("⚠ Баланс токенов на нуле. Пополните баланс, чтобы продолжить комфортно.")
            schedule_silence_check(msg.from_user.id, chat_id, delay_sec=600)
    finally:
        stop.set()
        try:
            await asyncio.wait_for(typer, timeout=0.1)
        except Exception:
            pass
        storage.set_user_chatting(msg.from_user.id, False)  # <-- диалог завершился