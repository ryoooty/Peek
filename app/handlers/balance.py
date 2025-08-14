
from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery


from app import storage

router = Router(name="balance")

BTN_BALANCE = "🪙 Токи"


def _balance_text(user_id: int) -> str:
    u = storage.get_user(user_id) or {}
    free_toki = int(u.get("free_toki") or 0)
    paid = int(u.get("paid_tokens") or 0)
    cache = int(u.get("cache_tokens") or 0)

    lines = [
        "<b>Баланс</b>",
        f"Бесплатные токи: <code>{free_toki}</code>",
        f"Платные токены: <code>{paid}</code>",
        f"Кэш‑токены: <code>{cache}</code>",
    ]
    log = storage.list_token_log(user_id, limit=5)
    if log:
        lines.append("")
        lines.append("<b>Проводки:</b>")
        for r in log:
            amt = int(r["amount"])
            sign = "+" if amt > 0 else ""
            meta = r.get("meta") or ""
            dt_str = str(r.get("created_at"))[:16]
            lines.append(f"{dt_str} {sign}{amt} {meta}")
    lines.append("")
    lines.append("Доступно: /promo CODE — активировать промокод")
    lines.append("Пополнить: /pay — создать заявку (временный режим)")
    return "\n".join(lines)


@router.message(Command("balance"))
async def cmd_balance(msg: Message):

    storage.ensure_user(msg.from_user.id, msg.from_user.username or None)
    await msg.answer(_balance_text(msg.from_user.id))


@router.message(F.text == BTN_BALANCE)
async def btn_balance(msg: Message):
    await cmd_balance(msg)



@router.callback_query(F.data == "open_balance")
async def cb_open_balance(call: CallbackQuery):

    await call.message.answer(_balance_text(call.from_user.id))
    await call.answer()

