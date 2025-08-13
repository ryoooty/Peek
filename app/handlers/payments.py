from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app import storage
from app.config import settings

router = Router(name="payments")


@router.message(Command("pay"))
async def cmd_pay(msg: Message):
    txt = (
        "Пополнение баланса:\n\n"
        "1) Boosty — переведите любую сумму и пришлите /confirm <сумма>.\n"
        "2) DonationAlerts — то же самое.\n\n"
        "После модерации токены будут начислены. Курс и детали — у админа."
    )
    await msg.answer(txt)


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
            pass
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
