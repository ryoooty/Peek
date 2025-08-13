# app/profile.py
from __future__ import annotations


from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app import storage
from app.config import settings
from app.scheduler import rebuild_user_jobs



router = Router(name="profile")


def _profile_text(u: dict) -> str:
    totals = storage.user_totals(u["tg_id"])
    top_line = "—"
    if totals["top_character"]:
        top_line = f"{totals['top_character']} ({totals['top_count']} сооб.)"
    sub = (u.get("subscription") or "free").lower()
    chats_total = len(storage.list_user_chats(u["tg_id"], page=1, page_size=9999))
    model = (u.get("default_model") or settings.default_model)
    live_on = bool(u.get("proactive_enabled") or 0)
    per_day = int(u.get("pro_per_day") or 2)
    gap_min = int(u.get("pro_min_gap_min") or 10)
    max_delay = int(u.get("pro_max_delay_min") or 720)
    return (
        "<b>Профиль</b>\n"
        f"Подписка: <b>{sub}</b>\n"
        f"Модель: <b>{model}</b>\n"
        f"Режим Live: {'🟢 Вкл' if live_on else '⚪ Выкл'}\n"
        f"Нуджей в сутки: <b>{per_day}</b>\n"
        f"Мин. интервал: <b>{gap_min} мин</b>\n"
        f"Макс. интервал: <b>{max_delay} мин</b>\n\n"
        f"Всего сообщений: <b>{totals['user_msgs'] + totals['ai_msgs']}</b>\n"
        f"Всего чатов: <b>{chats_total}</b>\n"
        f"Топ персонаж: <b>{top_line}</b>\n"
    )


def _profile_kb(u: dict):
    kb = InlineKeyboardBuilder()
    # 1 — модель
    kb.button(text=f"🤖 Модель: {u.get('default_model') or settings.default_model}", callback_data="prof:model")
    # 2 — баланс/подписка
    kb.button(text="💰 Баланс", callback_data="prof:balance")
    kb.button(text="🎫 Подписка", callback_data="prof:sub")
    # 3 — режим общения
    kb.button(text=f"💬 Режим: {u.get('default_chat_mode') or 'rp'}", callback_data="prof:mode")
    # 4 — настройки/инфо
    kb.button(text="⚙ Настройки", callback_data="prof:settings")
    kb.button(text="ℹ Инфо", callback_data="prof:info")
    kb.adjust(1, 2, 1, 2)
    return kb.as_markup()


@router.message(Command("profile"))
async def show_profile(msg: Message):
    storage.ensure_user(msg.from_user.id, msg.from_user.username or None)
    u = storage.get_user(msg.from_user.id) or {}
    await msg.answer(_profile_text(u), reply_markup=_profile_kb(u))


@router.callback_query(F.data == "prof:model")
async def cb_model(call: CallbackQuery):
    u = storage.get_user(call.from_user.id) or {}
    models = list(settings.model_tariffs.keys())
    cur = (u.get("default_model") or settings.default_model)
    nxt = models[(models.index(cur) + 1) % len(models)] if models else cur
    storage.set_user_field(call.from_user.id, "default_model", nxt)
    u = storage.get_user(call.from_user.id) or {}
    await call.message.edit_text(_profile_text(u), reply_markup=_profile_kb(u))
    await call.answer("Модель обновлена")


@router.callback_query(F.data == "prof:balance")
async def cb_balance(call: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅ Назад", callback_data="prof:back")
    kb.adjust(1)
    await call.message.edit_text(_balance_text(call.from_user.id), reply_markup=kb.as_markup())
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
    await call.message.edit_text(text, reply_markup=kb.as_markup())
    await call.answer()


@router.callback_query(F.data == "prof:mode")
async def cb_mode(call: CallbackQuery):
    u = storage.get_user(call.from_user.id) or {}
    new_mode = "live" if (u.get("default_chat_mode") or "rp") == "rp" else "rp"
    storage.set_user_field(call.from_user.id, "default_chat_mode", new_mode)
    u = storage.get_user(call.from_user.id) or {}
    await call.message.edit_text(_profile_text(u), reply_markup=_profile_kb(u))
    await call.answer("Режим обновлён")


@router.callback_query(F.data == "prof:settings")
async def cb_settings(call: CallbackQuery):
    u = storage.get_user(call.from_user.id) or {}
    kb = InlineKeyboardBuilder()
    # Убрали «📏 Длина ответов» (везде Авто). Остальное — как было.
    kb.button(text=f"🧩 Вид промтов ({u.get('default_resp_size') or 'auto'})", callback_data="set:prompts")
    kb.button(text="🗜 Автосжатие: {}".format('вкл' if settings.limits.auto_compress_default else 'выкл'), callback_data="set:compress")
    kb.button(text="⚡ Настройка Live", callback_data="set:live")
    kb.button(text="🌍 Часовой пояс", callback_data="set:tz")
    kb.button(text="⬅ Назад", callback_data="prof:back")
    kb.adjust(1)
    await call.message.edit_text("Настройки:", reply_markup=kb.as_markup())
    await call.answer()


@router.callback_query(F.data == "prof:info")
async def cb_info(call: CallbackQuery):
    await call.answer("Бот Peek. Настройки сохраняются автоматически. /reload перезагружает конфиг.")


@router.callback_query(F.data == "prof:back")
async def cb_back(call: CallbackQuery):
    u = storage.get_user(call.from_user.id) or {}
    await call.message.edit_text(_profile_text(u), reply_markup=_profile_kb(u))
    await call.answer()


# ---- Live Settings (как было, без «длины ответов») ----

@router.callback_query(F.data == "set:live")
async def cb_set_live(call: CallbackQuery):
    u = storage.get_user(call.from_user.id) or {}
    live_on = bool(u.get("proactive_enabled") or 0)
    kb = InlineKeyboardBuilder()
    kb.button(text=("🟢 Выключить Live" if live_on else "🟢 Включить Live"), callback_data="set:live:toggle")
    kb.button(text=f"В день: {int(u.get('pro_per_day') or 2)}", callback_data="set:live:per")
    kb.button(text=f"Окно: {u.get('pro_window_local') or '09:00-21:00'}", callback_data="set:live:win")
    kb.button(text=f"Пауза: {int(u.get('pro_min_gap_min') or 10)} мин", callback_data="set:live:gap")
    kb.button(text=f"Макс: {int(u.get('pro_max_delay_min') or 720)} мин", callback_data="set:live:max")
    kb.button(text="⬅ Назад", callback_data="prof:settings")
    kb.adjust(1)
    await call.message.edit_text(
        "Настройка Live:\n— Сообщения по случайным таймингам в течение суток.\n— Можно включить/выключить и настроить частоту.",
        reply_markup=kb.as_markup()
    )
    await call.answer()


@router.callback_query(F.data == "set:live:toggle")
async def cb_set_live_toggle(call: CallbackQuery):
    u = storage.get_user(call.from_user.id) or {}
    live_on = 0 if (u.get("proactive_enabled") or 0) else 1
    storage.set_user_field(call.from_user.id, "proactive_enabled", live_on)
    rebuild_user_jobs(call.from_user.id)
    # Сейчас окно не используется планировщиком, но оставим UI — совместимость.
    await cb_set_live(call)


@router.callback_query(F.data == "set:live:per")
async def cb_set_live_per(call: CallbackQuery):
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
    await cb_set_live(call)


@router.callback_query(F.data == "set:live:win")
async def cb_set_live_win(call: CallbackQuery):
    # UI сохраним, но планировщик окна не использует.
    u = storage.get_user(call.from_user.id) or {}
    win = (u.get("pro_window_local") or "09:00-21:00")
    presets = ["09:00-21:00", "10:00-22:00", "12:00-20:00", "08:00-18:00"]
    nxt = presets[(presets.index(win) + 1) % len(presets)]
    storage.set_user_field(call.from_user.id, "pro_window_local", nxt)
    # проставим совместимое UTC‑поле, если используется где‑то ещё
    tz = int((u.get("tz_offset_min") or 180))
    def _to_utc(w: str) -> str:
        a, b = w.split("-")
        parse = lambda s: int(s[:2]) * 60 + int(s[3:5])
        fmt = lambda m: f"{(m // 60) % 24:02d}:{m % 60:02d}"
        da, db = parse(a) - tz, parse(b) - tz
        return f"{fmt(da)}-{fmt(db)}"
    storage.set_user_field(call.from_user.id, "pro_window_utc", _to_utc(nxt))
    rebuild_user_jobs(call.from_user.id)
    await cb_set_live(call)


@router.callback_query(F.data == "set:live:gap")
async def cb_set_live_gap(call: CallbackQuery):
    u = storage.get_user(call.from_user.id) or {}
    val = int(u.get("pro_min_gap_min") or 10)
    cycle = [5, 10, 15, 30, 60, 120]

    
    try:
        nxt = cycle[(cycle.index(val) + 1) % len(cycle)]
    except ValueError:
        nxt = 10
    storage.set_user_field(call.from_user.id, "pro_min_gap_min", nxt)
    rebuild_user_jobs(call.from_user.id)
    await cb_set_live(call)

    


# ---- Другие настройки (оставлены) ----

@router.callback_query(F.data == "set:prompts")
async def cb_set_prompts(call: CallbackQuery):
    u = storage.get_user(call.from_user.id) or {}
    size = (u.get("default_resp_size") or "auto")
    order = ["small", "medium", "large", "auto"]  # в UI не показываем «длину», но вид промтов оставлен
    nxt = order[(order.index(size) + 1) % len(order)]
    storage.set_user_field(call.from_user.id, "default_resp_size", nxt)
    await cb_settings(call)


@router.callback_query(F.data == "set:compress")
async def cb_set_compress(call: CallbackQuery):
    settings.limits.auto_compress_default = not settings.limits.auto_compress_default
    await cb_settings(call)


@router.callback_query(F.data == "set:tz")
async def cb_set_tz(call: CallbackQuery):
    await call.message.edit_text(
        "Выберите часовой пояс:", reply_markup=tz_keyboard("tzprof")
    )
    await call.answer()


@router.callback_query(F.data.startswith("tzprof:"))
async def cb_tz_prof(call: CallbackQuery):
    try:
        offset = int(call.data.split(":", 1)[1])
    except Exception:
        await call.answer("Некорректное значение", show_alert=True)
        return
    storage.set_user_field(call.from_user.id, "tz_offset_min", offset)
    u = storage.get_user(call.from_user.id) or {}
    await call.message.edit_text(_profile_text(u), reply_markup=_profile_kb(u))
    await call.answer("Часовой пояс обновлён")


@router.message(Command("tz"))
async def cmd_tz(msg: Message):
    await msg.answer("Выберите часовой пояс:", reply_markup=tz_keyboard("tzprof"))
