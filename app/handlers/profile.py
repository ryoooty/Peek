# app/profile.py
from __future__ import annotations


from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app import storage
import sys


def _settings():
    return sys.modules["app.config"].settings
from app.scheduler import rebuild_user_jobs
from app.handlers.balance import _balance_text
from app.handlers.payments import cmd_pay
from app.utils.tz import tz_keyboard, parse_tz_offset, parse_tz_offset_cb
from app.utils.telegram import safe_edit_text




router = Router(name="profile")


def _profile_text(u: dict) -> str:
    uid = int(u.get("tg_id") or 0)
    totals = (
        storage.user_totals(uid)
        if uid
        else {
            "user_msgs": 0,
            "ai_msgs": 0,
            "in_tokens": 0,
            "out_tokens": 0,
            "top_character": None,
            "top_count": 0,
        }
    )
    top_line = "—"
    if totals["top_character"]:
        top_line = f"{totals['top_character']} ({totals['top_count']} сооб.)"
    sub = (u.get("subscription") or "free").lower()
    chats_total = (
        len(storage.list_user_chats(uid, page=1, page_size=9999)) if uid else 0
    )

    s = _settings()
    model = (u.get("default_model") or s.default_model)
    chat_on = bool(u.get("proactive_enabled") or 0)
    per_day = int(u.get("pro_per_day") or 2)
    gap_min = int(u.get("pro_min_gap_min") or 10)
    auto_cmp = s.limits.auto_compress_default
    return (
        "<b>Профиль</b>\n"
        f"Подписка: <b>{sub}</b>\n"
        f"Модель: <b>{model}</b>\n"
        f"Режим Чат: {'🟢 Вкл' if chat_on else '⚪ Выкл'}\n"
        f"Автосжатие: {'🗜 Вкл' if auto_cmp else '⚪ Выкл'}\n"
        f"Нуджей в сутки: <b>{per_day}</b>\n"
        f"Мин. интервал: <b>{gap_min} мин</b>\n\n"
        f"Всего сообщений: <b>{totals['user_msgs'] + totals['ai_msgs']}</b>\n"
        f"Всего чатов: <b>{chats_total}</b>\n"
        f"Топ персонаж: <b>{top_line}</b>\n"

    )



def _profile_kb(u: dict):
    kb = InlineKeyboardBuilder()
    # 1 — модель
    s = _settings()
    kb.button(text=f"🤖 Модель: {u.get('default_model') or s.default_model}", callback_data="prof:model")
    # 2 — токи
    kb.button(text="🪙 Токи", callback_data="prof:balance")
    # 3 — подписка
    kb.button(text="📣 Подписка", callback_data="prof:sub")
    # 4 — режим общения
    kb.button(text=f"💬 Режим: {u.get('default_chat_mode') or 'rp'}", callback_data="prof:mode")
    # 5 — настройки/инфо
    kb.button(text="⚙ Настройки", callback_data="prof:settings")
    kb.button(text="ℹ Инфо", callback_data="prof:info")
    kb.adjust(1, 1, 1, 1, 2)
    return kb.as_markup()


@router.message(Command("profile"))
async def show_profile(msg: Message):
    storage.ensure_user(msg.from_user.id, msg.from_user.username or None)
    u = storage.get_user(msg.from_user.id) or {}
    await msg.answer(_profile_text(u), reply_markup=_profile_kb(u))


@router.callback_query(F.data == "prof:model")
async def cb_model(call: CallbackQuery):
    u = storage.get_user(call.from_user.id) or {}
    s = _settings()
    models = list(s.model_tariffs)
    cur = u.get("default_model") or s.default_model
    try:
        idx = models.index(cur)
    except ValueError:
        idx = -1
    nxt = models[(idx + 1) % len(models)] if models else cur
    storage.set_user_field(call.from_user.id, "default_model", nxt)
    u = storage.get_user(call.from_user.id) or {}
    await safe_edit_text(call.message, _profile_text(u), callback=call, reply_markup=_profile_kb(u))
    await call.answer("Модель обновлена")


@router.callback_query(F.data == "prof:balance")
async def cb_balance(call: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="Пополнить баланс", callback_data="prof:pay")
    kb.button(text="⬅ Назад", callback_data="prof:back")
    kb.adjust(1)
    await safe_edit_text(
        call.message,
        _balance_text(call.from_user.id),
        callback=call,
        reply_markup=kb.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data == "prof:pay")
async def cb_pay(call: CallbackQuery):
    await cmd_pay(call.message)
    await call.answer()



@router.callback_query(F.data == "prof:sub")
async def cb_sub(call: CallbackQuery):
    u = storage.get_user(call.from_user.id) or {}
    text = (
        "Подписка управляется вручную. В планах — автоматизация.\n"
        "Текущий уровень: <b>{}</b>".format((u.get("subscription") or "free").lower())
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅ Назад", callback_data="prof:back")
    kb.adjust(1)
    await safe_edit_text(call.message, text, callback=call, reply_markup=kb.as_markup())
    await call.answer()


@router.callback_query(F.data == "prof:mode")
async def cb_mode(call: CallbackQuery):
    u = storage.get_user(call.from_user.id) or {}
    new_mode = "chat" if (u.get("default_chat_mode") or "rp") == "rp" else "rp"
    storage.set_user_field(call.from_user.id, "default_chat_mode", new_mode)
    storage.update_user_chats_mode(call.from_user.id, new_mode)
    u = storage.get_user(call.from_user.id) or {}
    await safe_edit_text(call.message, _profile_text(u), callback=call, reply_markup=_profile_kb(u))
    await call.answer("Режим обновлён")


@router.callback_query(F.data == "prof:settings")
async def cb_settings(call: CallbackQuery):
    u = storage.get_user(call.from_user.id) or {}
    kb = InlineKeyboardBuilder()
    s = _settings()
    kb.button(text="🗜 Автосжатие: {}".format('вкл' if s.limits.auto_compress_default else 'выкл'), callback_data="set:compress")
    kb.button(text="⚡ Настройка Чата", callback_data="set:chat")
    kb.button(text="🌍 Часовой пояс", callback_data="set:tz")
    kb.button(text="⬅ Назад", callback_data="prof:back")
    kb.adjust(1)
    await safe_edit_text(call.message, "Настройки:", callback=call, reply_markup=kb.as_markup())
    await call.answer()


@router.callback_query(F.data == "prof:info")
async def cb_info(call: CallbackQuery):
    await call.answer("Бот Peek. Настройки сохраняются автоматически. /reload перезагружает конфиг.")


@router.callback_query(F.data == "prof:back")
async def cb_back(call: CallbackQuery):
    u = storage.get_user(call.from_user.id) or {}
    await safe_edit_text(call.message, _profile_text(u), callback=call, reply_markup=_profile_kb(u))
    await call.answer()


# ---- Chat Settings (как было, без «длины ответов») ----

@router.callback_query(F.data == "set:chat")
async def cb_set_chat(call: CallbackQuery):
    u = storage.get_user(call.from_user.id) or {}

    chat_on = bool(u.get("proactive_enabled") or 0)
    kb = InlineKeyboardBuilder()
    kb.button(text=("🟢 Выключить Чат" if chat_on else "🟢 Включить Чат"), callback_data="set:chat:toggle")
    kb.button(text=f"В день: {int(u.get('pro_per_day') or 2)}", callback_data="set:chat:per")
    kb.button(text=f"Окно: {u.get('pro_window_local') or '09:00-21:00'}", callback_data="set:chat:win")
    kb.button(text=f"Пауза: {int(u.get('pro_min_gap_min') or 10)} мин", callback_data="set:chat:gap")
    kb.button(text=f"Макс. интервал: {int(u.get('pro_max_delay_min') or 240)} мин", callback_data="set:chat:max")
    kb.button(text="⬅ Назад", callback_data="prof:settings")
    kb.adjust(1)

    await safe_edit_text(
        call.message,
        "Настройка Чата:\n— Сообщения по случайным таймингам в течение суток.\n— Можно включить/выключить и настроить частоту.",
        callback=call,
        reply_markup=kb.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data == "set:chat:toggle")
async def cb_set_chat_toggle(call: CallbackQuery):
    u = storage.get_user(call.from_user.id) or {}
    chat_on = 0 if (u.get("proactive_enabled") or 0) else 1
    storage.set_user_field(call.from_user.id, "proactive_enabled", chat_on)
    rebuild_user_jobs(call.from_user.id)
    # Сейчас окно не используется планировщиком, но оставим UI — совместимость.
    await cb_set_chat(call)


@router.callback_query(F.data == "set:chat:per")
async def cb_set_chat_per(call: CallbackQuery):
    u = storage.get_user(call.from_user.id) or {}
    # Цикл значений: 2→3→5→1→2
    val = int(u.get("pro_per_day") or 2)
    cycle = [2, 3, 5, 1]
    try:
        nxt = cycle[(cycle.index(val) + 1) % len(cycle)]
    except ValueError:
        nxt = 2
    storage.set_user_field(call.from_user.id, "pro_per_day", nxt)
    rebuild_user_jobs(call.from_user.id)
    await cb_set_chat(call)


@router.callback_query(F.data == "set:chat:win")
async def cb_set_chat_win(call: CallbackQuery):
    # UI сохраним, но планировщик окна не использует.
    u = storage.get_user(call.from_user.id) or {}
    win = (u.get("pro_window_local") or "09:00-21:00")
    presets = ["09:00-21:00", "10:00-22:00", "12:00-20:00", "08:00-18:00"]
    try:
        nxt = presets[(presets.index(win) + 1) % len(presets)]
    except ValueError:
        nxt = presets[0]
    storage.set_user_field(call.from_user.id, "pro_window_local", nxt)
    # проставим совместимое UTC‑поле, если используется где‑то ещё
    tz_val = u.get("tz_offset_min")
    tz = int(tz_val if tz_val is not None else 180)
    def _to_utc(w: str) -> str:
        a, b = w.split("-")
        def parse(s: str) -> int:
            return int(s[:2]) * 60 + int(s[3:5])

        def fmt(m: int) -> str:
            return f"{(m // 60) % 24:02d}:{m % 60:02d}"

        da, db = parse(a) - tz, parse(b) - tz
        return f"{fmt(da)}-{fmt(db)}"
    storage.set_user_field(call.from_user.id, "pro_window_utc", _to_utc(nxt))
    rebuild_user_jobs(call.from_user.id)
    await cb_set_chat(call)



@router.callback_query(F.data == "set:chat:gap")
async def cb_set_chat_gap(call: CallbackQuery):
    u = storage.get_user(call.from_user.id) or {}
    val = int(u.get("pro_min_gap_min") or 10)
    cycle = [5, 10, 15, 30, 60, 120]
    try:
        nxt = cycle[(cycle.index(val) + 1) % len(cycle)]
    except ValueError:
        nxt = 10
    storage.set_user_field(call.from_user.id, "pro_min_gap_min", nxt)
    await cb_set_chat(call)


@router.callback_query(F.data == "set:chat:max")
async def cb_set_chat_max(call: CallbackQuery):
    u = storage.get_user(call.from_user.id) or {}
    val = int(u.get("pro_max_delay_min") or 240)
    cycle = [60, 120, 180, 240, 360, 720]
    try:
        nxt = cycle[(cycle.index(val) + 1) % len(cycle)]
    except ValueError:
        nxt = 240
    storage.set_user_field(call.from_user.id, "pro_max_delay_min", nxt)
    await cb_set_chat(call)


    


# ---- Другие настройки (оставлены) ----



@router.callback_query(F.data == "set:compress")
async def cb_set_compress(call: CallbackQuery):
    s = _settings()
    s.limits.auto_compress_default = not s.limits.auto_compress_default
    await cb_settings(call)


@router.callback_query(F.data == "set:tz")
async def cb_set_tz(call: CallbackQuery):
    await safe_edit_text(
        call.message,
        "Выберите часовой пояс:",
        callback=call,
        reply_markup=tz_keyboard(prefix="tzprof"),
    )
    await call.answer()


@router.callback_query(F.data.startswith("tzprof:"))
async def cb_tz_prof(call: CallbackQuery):
    data = call.data or ""
    if data.endswith(":skip"):
        offset_min = 0  # default to UTC
        msg = "Часовой пояс не задан. Используется UTC."
    else:
        try:
            offset_min = parse_tz_offset_cb(data)
        except ValueError:
            await call.answer("Некорректное значение", show_alert=True)
            return
        msg = "Часовой пояс обновлён"
    storage.set_user_field(call.from_user.id, "tz_offset_min", offset_min)
    u = storage.get_user(call.from_user.id) or {}
    await safe_edit_text(call.message, _profile_text(u), callback=call, reply_markup=_profile_kb(u))
    await call.answer(msg)


@router.message(Command("tz"))
async def cmd_tz(msg: Message):
    await msg.answer("Выберите часовой пояс:", reply_markup=tz_keyboard(prefix="tzprof"))


@router.message(lambda msg: parse_tz_offset(getattr(msg, "text", "")) is not None)
async def manual_tz_input(msg: Message):
    offset = parse_tz_offset(msg.text or "")
    if offset is None:
        return
    storage.set_user_field(msg.from_user.id, "tz_offset_min", offset)
    await msg.answer("Часовой пояс обновлён.")
