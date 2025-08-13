from __future__ import annotations

import math
from dataclasses import dataclass
from typing import AsyncGenerator, Dict, List, Tuple

from app import storage
from app.billing.pricing import calc_usage_cost
from app.config import settings
from app.character import get_system_prompt_for_chat
from app.providers.deepseek_openai import chat as provider_chat, stream_chat as provider_stream


@dataclass
class ChatReply:
    text: str
    usage_in: int = 0
    usage_out: int = 0
    billed: int = 0
    deficit: int = 0


def _collect_context(chat_id: int, *, limit: int = 50) -> List[dict]:
    msgs = storage.list_messages(chat_id, limit=limit)
    res: List[dict] = []
    for m in msgs:
        role = "user" if m["is_user"] else "assistant"
        res.append(dict(role=role, content=m["content"]))
    system_prompt = get_system_prompt_for_chat(chat_id)
    res = [dict(role="system", content=system_prompt)] + res
    return res


def _size_caps(resp_size: str) -> Tuple[int, int]:
    if resp_size == "small":
        return (220, 300)
    if resp_size == "medium":
        return (380, 600)
    if resp_size == "large":
        return (650, 900)
    return (700, 900)


def _safe_trim(text: str, char_limit: int) -> str:
    t = (text or "").strip()
    if len(t) <= char_limit:
        return t
    cut = t[:char_limit]
    pos = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"))
    return (cut if pos < 40 else cut[:pos + 1]).rstrip()


def _billable_tokens(model: str, usage_in: int, usage_out: int) -> int:
    t = settings.model_tariffs.get(model) or settings.model_tariffs.get(settings.default_model)
    if not t:
        return usage_in + usage_out
    units = (usage_in * t.input_per_1k + usage_out * t.output_per_1k) / 1000.0
    return max(1, int(math.ceil(units)))


def _apply_billing(user_id: int, model: str, usage_in: int, usage_out: int) -> Tuple[int, int]:
    """Возвращает (billed, deficit)."""
    billed = _billable_tokens(model, usage_in, usage_out)
    price_in, price_out, price_cache, total = calc_usage_cost(model, usage_in, usage_out)
    storage.log_usage(
        user_id,
        model,
        usage_in,
        usage_out,
        price_in,
        price_out,
        price_cache,
        total,
    )
    _spent_free, _spent_paid, deficit = storage.spend_tokens(user_id, billed)
    return billed, deficit


async def summarize_chat(chat_id: int, *, model: str, sentences: int = 4) -> str:
    msgs = storage.list_messages(chat_id, limit=40)
    parts: List[str] = []
    for m in msgs[-20:]:
        who = "User" if m["is_user"] else "Assistant"
        parts.append(f"{who}: {m['content']}")
    prompt = (
        "Суммируй диалог в 2–5 предложениях. Сохрани имена и намерения собеседников. "
        "Пиши кратко и по делу."
    )
    messages = [{"role": "system", "content": prompt}, {"role": "user", "content": "\n".join(parts)}]
    r = await provider_chat(
        model=model,
        messages=messages,
        temperature=0.3,
        max_tokens=220,
        timeout_s=settings.limits.request_timeout_seconds,
    )
    return _safe_trim(r.text, 700)


async def chat_turn(user_id: int, chat_id: int, text: str) -> ChatReply:
    user = storage.get_user(user_id) or {}
    ch = storage.get_chat(chat_id) or {}
    resp_size = (ch.get("resp_size") or user.get("default_resp_size") or "auto")
    toks_limit, char_limit = _size_caps(str(resp_size))

    messages = _collect_context(chat_id) + [dict(role="user", content=text)]
    model = (user.get("default_model") or settings.default_model)

    r = await provider_chat(
        model=model,
        messages=messages,
        temperature=0.7,
        max_tokens=toks_limit,
        timeout_s=settings.limits.request_timeout_seconds,
    )
    out_text = _safe_trim(r.text, char_limit)

    billed, deficit = _apply_billing(user_id, model, int(r.usage_in or 0), int(r.usage_out or 0))
    return ChatReply(
        text=out_text,
        usage_in=int(r.usage_in or 0),
        usage_out=int(r.usage_out or 0),
        billed=billed,
        deficit=deficit,
    )


async def live_stream(user_id: int, chat_id: int, text: str) -> AsyncGenerator[Dict[str, str], None]:
    """
    Live-режим: отдаём сырые дельты текста + финальные usage.
    Хендлер агрегирует в буфер и нарезает на сообщения.
    """
    user = storage.get_user(user_id) or {}
    ch = storage.get_chat(chat_id) or {}
    resp_size = (ch.get("resp_size") or user.get("default_resp_size") or "auto")
    toks_limit, _ = _size_caps(str(resp_size))

    model = (user.get("default_model") or settings.default_model)
    messages = _collect_context(chat_id) + [dict(role="user", content=text)]

    async for ev in provider_stream(
        model=model,
        messages=messages,
        temperature=0.7,
        max_tokens=toks_limit,
        timeout_s=settings.limits.request_timeout_seconds,
    ):
        if ev.get("type") == "delta":
            yield {"kind": "chunk", "text": ev.get("text") or ""}
        elif ev.get("type") == "usage":
            usage_in = int(ev.get("in") or 0)
            usage_out = int(ev.get("out") or 0)
            billed, deficit = _apply_billing(user_id, model, usage_in, usage_out)
            yield {
                "kind": "final",
                "usage_in": str(usage_in),
                "usage_out": str(usage_out),
                "billed": str(billed),
                "deficit": str(deficit),
            }
