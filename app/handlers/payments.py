from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from aiohttp import web
from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message

from app import storage
from app.config import settings

router = Router(name="payments")


# ----------------- Helpers -----------------
async def _notify_admins(text: str) -> None:
    """Send notification about topup to all admins."""
    if not settings.admin_ids:
        return
    try:
        async with Bot(token=settings.bot_token) as bot:
            for admin_id in settings.admin_ids:
                try:
                    await bot.send_message(admin_id, text)
                except Exception:
                    continue
    except Exception:
        # If bot can't be created we silently ignore – webhook should not fail
        pass


def _verify_signature(body: bytes, header_sig: str | None, secret: str | None) -> bool:
    if not secret:
        return True  # no secret -> skip check
    if not header_sig:
        return False
    mac = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, header_sig)


# ----------------- Webhooks -----------------
async def _handle_webhook(request: web.Request, provider: str, secret: str | None) -> web.Response:
    body = await request.read()
    if not _verify_signature(body, request.headers.get("X-Signature"), secret):
        return web.Response(status=403, text="invalid signature")
    try:
        payload: dict[str, Any] = json.loads(body.decode("utf-8"))
    except Exception:
        return web.Response(status=400, text="bad json")

    user_id = int(payload.get("user_id") or 0)
    amount = float(payload.get("amount") or 0)
    if not user_id or amount <= 0:
        return web.Response(status=400, text="invalid payload")

    tid = storage.create_topup_pending(user_id, amount, provider=provider)
    note = f"Заявка на пополнение #{tid}\nUser: {user_id}\nСумма: {amount}"
    await _notify_admins(note)
    return web.json_response({"status": "ok", "topup_id": tid})


async def boosty_webhook(request: web.Request) -> web.Response:
    return await _handle_webhook(request, "boosty", settings.boosty_secret)


async def donationalerts_webhook(request: web.Request) -> web.Response:
    return await _handle_webhook(request, "donationalerts", settings.donationalerts_secret)


def setup_webhooks(app: web.Application) -> None:
    """Register webhook endpoints on aiohttp app."""
    app.add_routes(
        [
            web.post("/boosty/webhook", boosty_webhook),
            web.post("/donationalerts/webhook", donationalerts_webhook),
        ]
    )


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
