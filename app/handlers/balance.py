from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app import storage

router = Router(name="balance")


def _balance_text(u: dict) -> str:
    return (
        "Баланс:\n"
        f"Токи (free): <b>{u.get('free_toki') or 0}</b>\n"
        f"Токены (paid): <b>{u.get('paid_tokens') or 0}</b>\n\n"
        "Пополнение — через /pay (после подтверждения токены будут зачислены)."
    )


@router.message(Command("balance"))
async def cmd_balance(msg: Message):
    storage.ensure_user(msg.from_user.id, msg.from_user.username or None)
    u = storage.get_user(msg.from_user.id) or {}
    await msg.answer(_balance_text(u))


@router.message(F.text == "💰 Баланс")
async def btn_balance(msg: Message):
    await cmd_balance(msg)


@router.callback_query(F.data == "open_balance")
async def cb_open_balance(call: CallbackQuery):
    u = storage.get_user(call.from_user.id) or {}
    await call.message.answer(_balance_text(u))
    await call.answer()

