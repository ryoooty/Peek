# app/handlers/admin.py
from __future__ import annotations

import time
import traceback
from pathlib import Path
from typing import Optional

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

from app import storage
from app.config import settings, reload_settings, BASE_DIR

router = Router(name="admin")

# --------- Constants / Paths ---------
MEDIA_DIR = Path(BASE_DIR) / "media" / "characters"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)


# --------- Helpers ---------
def _is_admin(uid: int) -> bool:
    try:
        return int(uid) in {int(x) for x in (settings.admin_ids or [])}
    except Exception:
        return False


async def _require_admin(msg_or_call) -> bool:
    uid = msg_or_call.from_user.id
    if not _is_admin(uid):
        # Молча игнорируем, чтобы не палить список админов
        return False
    return True


def _admin_kb() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text="🛠 Техработы on/off", callback_data="admin:maintenance")
    kb.button(text="🔄 Reload config", callback_data="admin:reload")
    kb.button(text="📨 Nudge now (self)", callback_data="admin:nudge")
    kb.button(text="📊 Диагностика", callback_data="admin:diag")
    kb.button(text="📈 Статистика", callback_data="admin:stats")
    kb.button(text="➕ Добавить персонажа", callback_data="admin:char_add_help")
    kb.button(text="🖼 Фото персонажа", callback_data="admin:char_photo_help")
    kb.adjust(2, 2, 2, 2)
    return kb


def _fmt_diag() -> str:
    try:
        u_cnt = storage._q("SELECT COUNT(*) c FROM users").fetchone()["c"]
        c_cnt = storage._q("SELECT COUNT(*) c FROM chats").fetchone()["c"]
        m_cnt = storage._q("SELECT COUNT(*) c FROM messages").fetchone()["c"]
        p_cnt = storage._q("SELECT COUNT(*) c FROM proactive_log").fetchone()["c"]
    except Exception:
        u_cnt = c_cnt = m_cnt = p_cnt = "?"
    mode = "ON" if settings.maintenance_mode else "OFF"
    model = settings.default_model
    return (
        "<b>Диагностика</b>\n"
        f"• Users: <b>{u_cnt}</b>\n"
        f"• Chats: <b>{c_cnt}</b>\n"
        f"• Messages: <b>{m_cnt}</b>\n"
        f"• Proactive log: <b>{p_cnt}</b>\n"
        f"• Maintenance: <b>{mode}</b>\n"
        f"• Default model: <code>{model}</code>\n"
    )


async def _nudge_self(uid: int) -> str:
    """
    Принудительно отправить Live-нудж самому себе в актуальный last_chat.
    """
    last = storage.get_last_chat(uid)
    if not last:
        return "❌ Нет последнего чата для отправки."
    chat_id = int(last["id"])

    fn = None
    # поддержим оба расположения доменной функции
    try:
        from app.domain.proactive import proactive_nudge as fn  # type: ignore
    except Exception:
        try:
            from app.proactive import proactive_nudge as fn  # type: ignore
        except Exception:
            fn = None

    if not fn:
        return "❌ Нет реализации proactive_nudge (app.domain.proactive или app.proactive)."

    try:
        # пробуем сигнатуру без bot
        txt = await fn(user_id=uid, chat_id=chat_id)  # type: ignore[misc]
        return "✅ Отправлено." if txt else "⚠ Ничего не отправлено (пустой текст)."
    except TypeError:
        # если требуется bot — сообщим явно
        return "⚠ Не удалось вызвать proactive_nudge: ожидается параметр bot."
    except Exception:
        return "❌ Ошибка при отправке:\n<pre>{}</pre>".format(
            (traceback.format_exc()[:1500]).replace("<", "&lt;")
        )


def _escape(s: str) -> str:
    return s.replace("<", "&lt;").replace(">", "&gt;")


# --------- /admin: панель ---------
@router.message(Command("admin"))
async def cmd_admin(msg: Message):
    if not await _require_admin(msg):
        return
    text = (
        "<b>Админ‑панель</b>\n"
        "Быстрые действия ниже. Команды:\n"
        "• /maintenance — переключить техработы\n"
        "• /reload — перечитать конфиг\n"
        "• /nudge_now — отправить Live себе\n"
        "• /diag — диагностика\n"
        "• /stats — статистика\n"
        "• /char_add, /char_photo — управление персонажами"
    )
    await msg.answer(text, reply_markup=_admin_kb().as_markup())


@router.callback_query(F.data.startswith("admin:"))
async def cb_admin(call: CallbackQuery):
    if not await _require_admin(call):
        return
    action = call.data.split(":", 1)[1]
    if action == "maintenance":
        settings.maintenance_mode = not settings.maintenance_mode
        await call.answer(f"Maintenance: {'ON' if settings.maintenance_mode else 'OFF'}", show_alert=True)
        await call.message.edit_text(_fmt_diag(), reply_markup=_admin_kb().as_markup())
        return
    if action == "reload":
        reload_settings()
        await call.answer("Reloaded ✅", show_alert=True)
        await call.message.edit_text(_fmt_diag(), reply_markup=_admin_kb().as_markup())
        return
    if action == "nudge":
        res = await _nudge_self(call.from_user.id)
        await call.answer(res, show_alert=True)
        return
    if action == "diag":
        await call.message.edit_text(_fmt_diag(), reply_markup=_admin_kb().as_markup())
        await call.answer()
        return
    if action == "stats":
        # сейчас stats ~= diag; можно расширить
        await call.message.edit_text(_fmt_diag(), reply_markup=_admin_kb().as_markup())
        await call.answer()
        return
    if action == "char_add_help":
        await call.answer("Использование:\n/char_add Имя [фандом] [краткая_инфа]", show_alert=True)
        return
    if action == "char_photo_help":
        await call.answer("Пришлите фото с подписью:\n/char_photo <id>", show_alert=True)
        return


# --------- Технические команды ---------
@router.message(Command("maintenance"))
async def cmd_maintenance(msg: Message):
    if not await _require_admin(msg):
        return
    settings.maintenance_mode = not settings.maintenance_mode
    await msg.answer(f"Maintenance: {'ON' if settings.maintenance_mode else 'OFF'}")


@router.message(Command("reload"))
async def cmd_reload(msg: Message):
    if not await _require_admin(msg):
        return
    reload_settings()
    await msg.answer("Config reloaded ✅")


@router.message(Command("nudge_now"))
async def cmd_nudge_now(msg: Message):
    if not await _require_admin(msg):
        return
    res = await _nudge_self(msg.from_user.id)
    await msg.answer(res)


@router.message(Command("diag"))
async def cmd_diag(msg: Message):
    if not await _require_admin(msg):
        return
    await msg.answer(_fmt_diag())


@router.message(Command("stats"))
async def cmd_stats(msg: Message):
    if not await _require_admin(msg):
        return
    await msg.answer(_fmt_diag())


# --------- Персонажи ---------
@router.message(Command("char_add"))
async def cmd_char_add(msg: Message):
    if not await _require_admin(msg):
        return
    # /char_add <name> [fandom] [info_short...]
    parts = (msg.text or "").split(maxsplit=2)
    if len(parts) < 2:
        return await msg.answer(
            "Использование: /char_add <имя> [фандом] [краткая_инфа]\n"
            "Пример: <code>/char_add Furina Genshin 'Hydro Archon'</code>"
        )
    name = parts[1]
    fandom = None
    info = None
    if len(parts) >= 3:
        tmp = parts[2].split(maxsplit=1)
        fandom = tmp[0]
        info = tmp[1] if len(tmp) > 1 else None
    cid = storage.ensure_character(name, fandom=fandom, info_short=info)
    await msg.answer(
        f"Персонаж «{_escape(name)}» создан (id=<code>{cid}</code>).\n"
        "Пришлите фото с подписью: <code>/char_photo &lt;id&gt;</code>"
    )


@router.message(Command("char_photo"))
async def cmd_char_photo(msg: Message):
    if not await _require_admin(msg):
        return
    # Разбираем char_id из текста или подписи (на случай фото с подписью)
    char_id: Optional[int] = None
    for source in (msg.text or "", msg.caption or ""):
        if not source:
            continue
        ps = source.split()
        if len(ps) >= 2 and ps[0] == "/char_photo":
            try:
                char_id = int(ps[1])
                break
            except Exception:
                pass
    if not char_id:
        return await msg.answer(
            "Использование: отправьте фото с подписью: <code>/char_photo &lt;id&gt;</code>"
        )

    # file_id из текущего сообщения или из reply
    file_id: Optional[str] = None
    if msg.photo:
        file_id = msg.photo[-1].file_id
    elif msg.reply_to_message and msg.reply_to_message.photo:
        file_id = msg.reply_to_message.photo[-1].file_id
    if not file_id:
        return await msg.answer(
            "Пришлите фото с подписью команды или ответом на фото.\n"
            "Пример: <code>/char_photo 123</code>"
        )

    # Скачиваем фото в media/characters/<id>_<ts>.<ext>
    try:
        fl = await msg.bot.get_file(file_id)
        ext = Path(fl.file_path or "photo.jpg").suffix or ".jpg"
        save_name = f"{char_id}_{int(time.time())}{ext}"
        save_path = MEDIA_DIR / save_name
        await msg.bot.download(file=fl.file_id, destination=save_path)
    except TelegramBadRequest:
        # fallback: другие версии aiogram могут требовать объект get_file(...) в download
        try:
            fl = await msg.bot.get_file(file_id)
            ext = Path(fl.file_path or "photo.jpg").suffix or ".jpg"
            save_name = f"{char_id}_{int(time.time())}{ext}"
            save_path = MEDIA_DIR / save_name
            await msg.bot.download(file=fl, destination=save_path)
        except Exception as e:
            return await msg.answer(f"Не удалось скачать фото: <code>{_escape(str(e))}</code>")
    except Exception as e:
        return await msg.answer(f"Не удалось скачать фото: <code>{_escape(str(e))}</code>")

    # Пытаемся сохранить путь; если нет такой функции — сохраним file_id
    try:
        storage.set_character_photo_path(char_id, str(save_path.as_posix()))  # type: ignore[attr-defined]
    except Exception:
        # старый фолбэк
        storage.set_character_photo(char_id, file_id)

    await msg.answer("Фото сохранено ✅\nПуть: <code>{_}</code>".format(_=save_path.as_posix()))
