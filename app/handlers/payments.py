
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from aiohttp import web
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
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
    tokens = int(amount * 1000)
    tid = storage.create_topup_pending(user_id, tokens, amount)
    storage.attach_receipt(tid, "-")
    storage.approve_topup(tid, admin_id=0)
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
    tokens = int(amount * 1000)
    tid = storage.create_topup_pending(user_id, tokens, amount)
    storage.attach_receipt(tid, "-")
    storage.approve_topup(tid, admin_id=0)
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
    tid = storage.create_topup_pending(call.from_user.id, tokens, price)
    storage.attach_receipt(tid, "-")
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
        price = float(parts[1].replace(",", "."))
    except Exception:
        return await msg.answer("Некорректная сумма.")
    tokens = int(price * 1000)
    tid = storage.create_topup_pending(msg.from_user.id, tokens, price)
    # Уведомление админам
    note = (
        f"Заявка на пополнение #{tid}\nUser: {msg.from_user.id}\n"
        f"Сумма: {price} ₽ ({tokens} токенов)"
    )
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
    storage.attach_receipt(topup["id"], msg.document.file_id)
    await msg.answer("Чек получен, ожидайте подтверждения")

    u = storage.get_user(msg.from_user.id) or {}
    balance = int(u.get("free_toki") or 0) + int(u.get("paid_tokens") or 0)
    caption = (
        f"Заявка #{topup['id']}\n"
        f"file_id: {msg.document.file_id}\n"
        f"User: {msg.from_user.id}\n"
        f"Баланс: {balance}\n"
        f"Сумма: {topup['amount']}\n"
        f"Токены: {topup['tokens']}"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅", callback_data=f"topup:approve:{topup['id']}"
                ),
                InlineKeyboardButton(
                    text="🚫", callback_data=f"topup:decline:{topup['id']}"
                ),
                InlineKeyboardButton(
                    text="➡️", callback_data=f"topup:skip:{topup['id']}"
                ),
            ]
        ]
    )
    for admin_id in settings.admin_ids:
        try:
            await msg.bot.send_document(
                admin_id, msg.document.file_id, caption=caption, reply_markup=kb
            )
        except Exception:
            logger.exception(
                "Failed to notify admin %s about topup %s", admin_id, topup["id"]
            )


@router.callback_query(F.data.startswith("topup:"))
async def cb_topup(call: CallbackQuery):
    if call.from_user.id not in settings.admin_ids:
        return await call.answer()
    try:
        _, action, tid_s = (call.data or "").split(":", 2)
        tid = int(tid_s)
    except Exception:
        return await call.answer("Некорректный запрос", show_alert=True)

    topup = storage.get_topup(tid)
    if not topup:
        return await call.answer("Не найдено", show_alert=True)

    if action == "approve":
        ok = storage.approve_topup(tid, call.from_user.id)
        if ok:
            await call.message.edit_caption(
                (call.message.caption or "") + "\n\n✅ Одобрено", reply_markup=None
            )
            try:
                await call.bot.send_message(
                    topup["user_id"], f"Счёт #{tid} одобрен. Баланс пополнен."
                )
            except Exception:
                logger.exception(
                    "Failed to notify user %s about topup %s",
                    topup["user_id"],
                    tid,
                )
            return await call.answer("Одобрено")
        return await call.answer("Не удалось", show_alert=True)
    if action == "decline":
        ok = storage.decline_topup(tid, call.from_user.id)
        if ok:
            await call.message.edit_caption(
                (call.message.caption or "") + "\n\n🚫 Отклонено", reply_markup=None
            )
            try:
                await call.bot.send_message(
                    topup["user_id"], f"Счёт #{tid} отклонён."
                )
            except Exception:
                logger.exception(
                    "Failed to notify user %s about topup %s",
                    topup["user_id"],
                    tid,
                )
            return await call.answer("Отклонено")
        return await call.answer("Не удалось", show_alert=True)
    if action == "skip":
        await call.message.edit_reply_markup(None)
        return await call.answer("Пропущено")


