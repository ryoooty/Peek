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
    spent_rub = storage.total_usage_cost_rub(user_id)
    return (
        "<b>Баланс</b>\n"
        f"Бесплатные токи: <code>{free_toki}</code>\n"
        f"Платные токены: <code>{paid}</code>\n"
        f"Кэш‑токены: <code>{cache}</code>\n"
        f"Потрачено: <code>{spent_rub:.4f} ₽</code>\n\n"
        "Доступно: /promo CODE — активировать промокод\n"
        "Пополнить: /pay — создать заявку (временный режим)"
    )


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
