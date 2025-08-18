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
    if storage.has_pending_topup(msg.from_user.id):
        return await msg.answer("Ваша предыдущая заявка ещё не обработана.")
    tid = storage.create_topup_pending(msg.from_user.id, amount, provider="manual")
    # Уведомление админам
    note = f"Заявка на пополнение #{tid}\nUser: {msg.from_user.id}\nСумма: {amount}"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Подтвердить", callback_data=f"topup:approve:{tid}"),
                InlineKeyboardButton(text="Отклонить", callback_data=f"topup:decline:{tid}"),
                InlineKeyboardButton(text="Пропустить", callback_data=f"topup:skip:{tid}"),
            ]
        ]
    )
    for admin_id in settings.admin_ids:
        try:
            await msg.bot.send_message(admin_id, note, reply_markup=kb)
        except Exception:
            logger.exception("Failed to notify admin %s about topup %s", admin_id, tid)
    await msg.answer("Заявка отправлена на модерацию. Спасибо!")


@router.callback_query(F.data.startswith("topup:approve:"))
async def cb_topup_approve(call: CallbackQuery):
    if call.from_user.id not in settings.admin_ids:
        return await call.answer()
    try:
        tid = int((call.data or "").split(":")[2])
    except Exception:
        return await call.answer("Некорректный запрос", show_alert=True)
    topup = storage.get_topup(tid)
    if not topup or topup["status"] != "pending":
        return await call.answer("Заявка уже обработана", show_alert=True)
    storage.approve_topup(tid, call.from_user.id)
    await call.answer("✅ Одобрено")
    try:
        await call.bot.send_message(
            topup["user_id"],
            f"✅ Счёт #{tid} на {topup['amount']} подтверждён, баланс пополнен.",
        )
    except Exception:
        logger.exception(
            "Failed to notify user %s about approved topup %s",
            topup["user_id"],
            tid,
        )
    try:
        await call.message.edit_reply_markup()
    except Exception:
        pass


@router.callback_query(F.data.startswith("topup:decline:"))
async def cb_topup_decline(call: CallbackQuery):
    if call.from_user.id not in settings.admin_ids:
        return await call.answer()
    try:
        tid = int((call.data or "").split(":")[2])
    except Exception:
        return await call.answer("Некорректный запрос", show_alert=True)
    topup = storage.get_topup(tid)
    if not topup or topup["status"] != "pending":
        return await call.answer("Заявка уже обработана", show_alert=True)
    storage.delete_topup(tid)
    await call.answer("🚫 Отклонено")
    support_link = ""
    if settings.support_id:
        support_link = f'\n<a href="tg://user?id={settings.support_id}">Поддержка</a>'
    try:
        await call.bot.send_message(
            topup["user_id"],
            f"🚫 Заявка #{tid} отклонена.{support_link}",
            parse_mode="HTML",
        )
    except Exception:
        logger.exception(
            "Failed to notify user %s about declined topup %s",
            topup["user_id"],
            tid,
        )
    try:
        await call.message.edit_reply_markup()
    except Exception:
        pass


@router.callback_query(F.data.startswith("topup:skip:"))
async def cb_topup_skip(call: CallbackQuery):
    if call.from_user.id not in settings.admin_ids:
        return await call.answer()
    try:
        tid = int((call.data or "").split(":")[2])
    except Exception:
        return await call.answer("Некорректный запрос", show_alert=True)
    topup = storage.get_topup(tid)
    if not topup or topup["status"] != "pending":
        return await call.answer("Заявка уже обработана", show_alert=True)
    await call.answer("⏭ Пропущено")


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
