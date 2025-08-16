from __future__ import annotations

import hashlib
import hmac
import json
import logging
from aiohttp import web
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app import storage
from app.config import settings

logger = logging.getLogger(__name__)

router = Router(name="payments")
http_router = web.RouteTableDef()


def _verify_signature(secret: str | None, body: bytes, header_sig: str | None) -> bool:
    if not secret or not header_sig:
        return False
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, header_sig)


@http_router.post("/boosty/webhook")
async def boosty_webhook(req: web.Request) -> web.Response:
    body = await req.read()
    if not _verify_signature(settings.boosty_secret, body, req.headers.get("X-Signature")):
        return web.Response(status=403)
    try:
        payload = json.loads(body.decode("utf-8"))
        user_id = int(payload.get("user_id"))
        amount = float(payload.get("amount"))
    except Exception:
        logger.warning("bad boosty webhook payload", exc_info=True)
        return web.Response(status=400)
    storage.create_topup_pending(user_id, amount, provider="boosty")
    return web.Response(text="ok")


@http_router.post("/donationalerts/webhook")
async def donationalerts_webhook(req: web.Request) -> web.Response:
    body = await req.read()
    if not _verify_signature(
        settings.donationalerts_secret, body, req.headers.get("X-Signature")
    ):
        return web.Response(status=403)
    try:
        payload = json.loads(body.decode("utf-8"))
        user_id = int(payload.get("user_id"))
        amount = float(payload.get("amount"))
    except Exception:
        logger.warning("bad donationalerts webhook payload", exc_info=True)
        return web.Response(status=400)
    storage.create_topup_pending(user_id, amount, provider="donationalerts")
    return web.Response(text="ok")


@router.message(Command("pay"))
async def cmd_pay(msg: Message):
    kb = InlineKeyboardBuilder()
    for opt in settings.pay_options:
        tokens = getattr(opt, "tokens", opt.get("tokens"))
        price = getattr(opt, "price_rub", opt.get("price_rub"))
        emoji = getattr(opt, "emoji", opt.get("emoji")) or ""
        text = f"{emoji + ' ' if emoji else ''}{tokens} — {price} ₽"
        kb.button(text=text, callback_data=f"buy:{tokens}")
    kb.adjust(2)
    kb.row(InlineKeyboardButton(text="🪙 Мой баланс", callback_data="open_balance"))
    await msg.answer("Пополнение баланса", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("buy:"))
async def cb_buy(call: CallbackQuery):
    await call.answer("Покупка временно недоступна", show_alert=True)


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
