from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app import storage


router = Router(name="balance")

BTN_BALANCE = "💰 Баланс"


def _balance_text(u: dict) -> str:
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


async def _send_balance(
    user_id: int,
    answer: Callable[[str], Awaitable[Any]],
    username: str | None = None,
) -> None:
    storage.ensure_user(user_id, username)
    u = storage.get_user(user_id) or {}
    await answer(_balance_text(u))


@router.message(Command("balance"))
async def cmd_balance(msg: Message) -> None:
    await _send_balance(msg.from_user.id, msg.answer, msg.from_user.username or None)


@router.message(F.text == BTN_BALANCE)
async def btn_balance(msg: Message) -> None:
    await _send_balance(msg.from_user.id, msg.answer, msg.from_user.username or None)


@router.callback_query(F.data == "open_balance")
async def cb_open_balance(call: CallbackQuery) -> None:
    await _send_balance(
        call.from_user.id, call.message.answer, call.from_user.username or None
    )
    await call.answer()

