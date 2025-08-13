
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
# app/handlers/balance.py
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from app import storage

router = Router(name="balance")


def _balance_text(u: dict) -> str:
    ops = storage.get_toki_log(int(u.get("tg_id")), limit=5)
    journal = ""
    if ops:
        journal_lines = [
            f"{r['created_at'][:16]} {r['meta'] or ''}: {int(r['amount'])}" for r in ops
        ]
        journal = "\n\nПоследние операции:\n" + "\n".join(journal_lines)
    return (
        "Баланс:\n"
        f"Токи (free): <b>{u.get('free_toki') or 0}</b>\n"
        f"Токены (paid): <b>{u.get('paid_tokens') or 0}</b>\n\n"
        "Пополнение — через /pay (после подтверждения токены будут зачислены)."
        + journal
    )

@router.message(Command("balance"))
async def cmd_balance(msg: Message):
    storage.ensure_user(msg.from_user.id, msg.from_user.username or None)
    u = storage.get_user(msg.from_user.id) or {}
    await msg.answer(_balance_text(u))  # <-- НОВОЕ сообщение

# reply-кнопка "💰 Баланс" из главного меню
@router.message(F.text == "💰 Баланс")
async def btn_balance(msg: Message):
    await cmd_balance(msg)



# Если где-то остались инлайн‑кнопки, ведущие к «балансу», — отвечаем НОВЫМ сообщением.
@router.callback_query(F.data == "open_balance")
async def cb_open_balance(call: CallbackQuery):
    await call.message.answer(_balance_text(call.from_user.id))
    await call.answer()
