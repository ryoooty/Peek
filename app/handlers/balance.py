from __future__ import annotations
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from app import storage

router = Router(name="balance")

BTN_BALANCE = "💰 Баланс"


def _balance_text(user_id: int) -> str:
    u = storage.get_user(user_id) or {}
    free_toki = int(u.get("free_toki") or 0)
    paid = int(u.get("paid_tokens") or 0)
    cache = int(u.get("cache_tokens") or 0)
    return (
        "<b>Баланс</b>\n"
        f"Бесплатные токи: <code>{free_toki}</code>\n"
        f"Платные токены: <code>{paid}</code>\n"
        f"Кэш‑токены: <code>{cache}</code>\n\n"
        "Доступно: /promo CODE — активировать промокод\n"
        "Пополнить: /pay — создать заявку (временный режим)"
    )


async def _show_balance(message: Message, user_id: int, username: str | None = None):
    storage.ensure_user(user_id, username)
    await message.answer(_balance_text(user_id))


@router.message(Command("balance"))
@router.message(F.text == BTN_BALANCE)
async def cmd_balance(msg: Message):
    await _show_balance(msg, msg.from_user.id, msg.from_user.username or None)


@router.callback_query(F.data == "open_balance")
async def cb_open_balance(call: CallbackQuery):
    await _show_balance(call.message, call.from_user.id, call.from_user.username or None)
    await call.answer()
