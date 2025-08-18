
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from aiohttp import web
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery

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
    text = (
        f"Счёт #{tid}: {tokens} токенов за {price} ₽\n"
        f"{settings.payment_details}"
    )
    await call.message.answer(text)
    await call.answer()


@router.message(Command("confirm"))
async def cmd_confirm(msg: Message):
    parts = (msg.text or msg.caption or "").split(maxsplit=1)
    if len(parts) < 2:
        return await msg.answer("Укажите сумму: /confirm 150")
    try:
        amount = float(parts[1].replace(",", "."))
    except Exception:
        return await msg.answer("Некорректная сумма.")

    doc = msg.document
    if doc and (
        doc.mime_type != "application/pdf" or int(doc.file_size or 0) > 5_000_000
    ):
        await msg.answer("Чек должен быть в формате PDF и не более 5 МБ. Он не прикреплён к заявке.")
        doc = None

    tid = storage.create_topup_pending(msg.from_user.id, amount, provider="manual")
    # Уведомление админам
    note = f"Заявка на пополнение #{tid}\nUser: {msg.from_user.id}\nСумма: {amount}"
    for admin_id in settings.admin_ids:
        try:
            if doc:
                await msg.bot.send_document(admin_id, doc.file_id, caption=note)
            else:
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
        tokens = int((call.data or "").split(":", 1)[1])
    except Exception:
        return await call.answer("Некорректный запрос", show_alert=True)

    if storage.get_active_topup(call.from_user.id):
        return await call.answer("У вас уже есть активная заявка", show_alert=True)

    option = None
    for opt in settings.pay_options:
        opt_tokens = int(getattr(opt, "tokens", opt.get("tokens")))
        if opt_tokens == tokens:
            option = opt
            break

    if not option:
        return await call.answer("Опция недоступна", show_alert=True)

    price = float(getattr(option, "price_rub", option.get("price_rub")))
    tid = storage.create_manual_topup(call.from_user.id, tokens, price)
    await call.message.answer(
        f"Счёт #{tid}: {tokens} токенов за {price} ₽\n{settings.pay_requisites}\nЗагрузите PDF-чек ответом на это сообщение",
    )
    await call.answer()


@router.message(F.document.mime_type == "application/pdf")
async def doc_receipt(msg: Message):
    topup = storage.get_active_topup(msg.from_user.id)
    if not topup or topup.get("status") != "waiting_receipt":
        await msg.answer("Нет активной заявки.")
        return
    parts = (msg.text or "").split()
    if len(parts) < 2:
        return await msg.answer("Использование: /decline <topup_id>")
    try:
        tid = int(parts[1])
    except Exception:
        return await msg.answer("Неверный id.")
    uid = storage.decline_topup(tid, msg.from_user.id)
    if not uid:
        return await msg.answer("Не удалось отклонить.")
    await msg.answer("🚫 Заявка отклонена")
    note = f"❌ Ваше пополнение #{tid} отклонено."
    if settings.support_user_id:
        note += (
            f"\nНапишите администратору: tg://user?id={settings.support_user_id}"
        )
    elif settings.support_chat_id:
        note += f"\nНапишите в чат поддержки: {settings.support_chat_id}"
    try:
        await msg.bot.send_message(uid, note)
    except Exception:
        logger.exception(
            "Failed to notify user %s about topup decline %s", uid, tid
        )

