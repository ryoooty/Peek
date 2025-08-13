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

        "Доступно: /promo CODE — активировать промокод\n"
        "Пополнить: /pay — создать заявку (временный режим)"
    )





@router.callback_query(F.data == "open_balance")
async def cb_open_balance(call: CallbackQuery):

    await call.answer()
