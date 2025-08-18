from __future__ import annotations

import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery

from app import storage
from app.config import settings

logger = logging.getLogger(__name__)

router = Router(name="payments")

@router.message(Command("pay"))
async def cmd_pay(msg: Message):
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for opt in settings.pay_options:
        tokens = getattr(opt, "tokens", opt.get("tokens"))
        price = getattr(opt, "price_rub", opt.get("price_rub"))
        emoji = getattr(opt, "emoji", opt.get("emoji")) or ""
        text = f"{emoji + ' ' if emoji else ''}{tokens} — {price} ₽"
        row.append(InlineKeyboardButton(text=text, callback_data=f"buy:{tokens}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="🪙 Мой баланс", callback_data="open_balance")])
    await msg.answer(
        "Пополнение баланса", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )


@router.callback_query(F.data.startswith("buy:"))
async def cb_buy(call: CallbackQuery):
    try:
        tokens = int((call.data or "").split(":", 1)[1])
    except Exception:
        return await call.answer("Некорректный запрос", show_alert=True)

    option = None
    for opt in settings.pay_options:
        opt_tokens = int(getattr(opt, "tokens", opt.get("tokens")))
        if opt_tokens == tokens:
            option = opt
            break

    if not option:
        return await call.answer("Опция недоступна", show_alert=True)

    price = float(getattr(option, "price_rub", option.get("price_rub")))
    amount = tokens / 1000.0
    tid = storage.create_topup_pending(call.from_user.id, amount, provider="manual")
    storage.approve_topup(tid, admin_id=0)
    await call.message.answer(
        f"Счёт #{tid}: {tokens} токенов за {price} ₽\n✅ Баланс пополнен",
    )
    await call.answer()


@router.message(Command("confirm"))
async def cmd_confirm(msg: Message):
    parts = (msg.text or "").split(maxsplit=1)
    if len(parts) < 2:
        return await msg.answer("Укажите сумму: /confirm 150")
    try:
        amount = float(parts[1].replace(",", "."))
    except Exception:
        return await msg.answer("Некорректная сумма.")
    tid = storage.create_topup_pending(msg.from_user.id, amount, provider="manual")
    # Уведомление админам
    note = f"Заявка на пополнение #{tid}\nUser: {msg.from_user.id}\nСумма: {amount}"
    for admin_id in settings.admin_ids:
        try:
            await msg.bot.send_message(admin_id, note)
        except Exception:
            logger.exception("Failed to notify admin %s about topup %s", admin_id, tid)
    await msg.answer("Заявка отправлена на модерацию. Спасибо!")


@router.message(Command("approve"))
async def cmd_approve(msg: Message):
    if msg.from_user.id not in settings.admin_ids:
        return
    parts = (msg.text or "").split()
    if len(parts) < 2:
        return await msg.answer("Использование: /approve <topup_id>")
    try:
        tid = int(parts[1])
    except Exception:
        return await msg.answer("Неверный id.")
    ok = storage.approve_topup(tid, msg.from_user.id)
    await msg.answer("✅ Заявка одобрена" if ok else "Не удалось одобрить.")


@router.message(Command("decline"))
async def cmd_decline(msg: Message):
    if msg.from_user.id not in settings.admin_ids:
        return
    parts = (msg.text or "").split()
    if len(parts) < 2:
        return await msg.answer("Использование: /decline <topup_id>")
    try:
        tid = int(parts[1])
    except Exception:
        return await msg.answer("Неверный id.")
    ok = storage.decline_topup(tid, msg.from_user.id)
    await msg.answer("🚫 Заявка отклонена" if ok else "Не удалось отклонить.")
