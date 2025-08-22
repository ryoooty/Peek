
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import AsyncGenerator

from app import storage
from app.billing.pricing import calc_usage_cost_rub
from app.config import settings
from app.providers.deepseek_openai import (
    chat as provider_chat,
    stream_chat as provider_stream,
)

logger = logging.getLogger(__name__)

DEFAULT_TOKENS_LIMIT = 700
DEFAULT_CHAR_LIMIT = 900

@dataclass
class ChatReply:
    text: str
    usage_in: int = 0
    usage_out: int = 0
    billed: int = 0
    deficit: int = 0
    cost_in: float = 0.0
    cost_out: float = 0.0
    cost_cache: float = 0.0
    cost_total: float = 0.0


def _approx_tokens(text: str) -> int:
    """Very rough token estimator."""
    return max(1, len(text or "") // 4)


async def _collect_context(
    chat_id: int,
    *,
    user_id: int,
    model: str,
    limit: int = 50,
    query: str | None = None,
) -> list[dict]:
    msgs = storage.list_messages(chat_id, limit=limit)
    seen_ids = {m["id"] for m in msgs}
    res: list[dict] = []
    for m in msgs:
        role = "user" if m["is_user"] else "assistant"
        res.append(dict(role=role, content=m["content"]))

    from app import character as _character

    if getattr(_character, "storage", None) is not storage:  # pragma: no cover - test hook
        _character.storage = storage  # type: ignore

    system_prompt = _character.get_system_prompt_for_chat(chat_id)
    res = [dict(role="system", content=system_prompt)] + res

    threshold = int(settings.limits.context_threshold_tokens or 0)
    total_tokens = sum(_approx_tokens(m["content"]) for m in res)
    if threshold and total_tokens > threshold:
        summary = await summarize_chat(chat_id, model=model)
        storage.compress_history(
            chat_id,
            summary.text,
            usage_in=summary.usage_in,
            usage_out=summary.usage_out,
        )
        _apply_billing(user_id, chat_id, model, summary.usage_in, summary.usage_out)
        storage.add_cache_tokens(chat_id, summary.usage_out - summary.usage_in)
        tail = res[1:][-20:]
        res = [
            dict(role="system", content=system_prompt),
            dict(role="system", content=summary.text),
        ] + tail
    if query:
        for m in storage.search_messages(chat_id, query, limit=5):
            if m["id"] in seen_ids:
                continue
            role = "user" if m["is_user"] else "assistant"
            res.append(dict(role=role, content=m["content"]))
    return res


def _safe_trim(text: str, char_limit: int) -> str:
    t = (text or "").strip()
    if len(t) <= char_limit:
        return t
    cut = t[:char_limit]
    pos = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"))
    return (cut if pos < 40 else cut[:pos + 1]).rstrip()


def _billable_tokens(
    model: str, usage_in: int, usage_out: int, cache_tokens: int
) -> int:
    t = settings.model_tariffs.get(model) or settings.model_tariffs.get(
        settings.default_model
    )
    if not t:
        return usage_in + usage_out + cache_tokens
    units = (
        usage_in * t.input_per_1k
        + usage_out * t.output_per_1k
        + cache_tokens * t.cache_per_1k
    ) / 1000.0
    return max(1, int(math.ceil(units)))


def _apply_billing(
    user_id: int,
    chat_id: int,
    model: str,
    usage_in: int,
    usage_out: int,
    cache_tokens: int | None = None,
) -> tuple[int, int]:
    """Возвращает (billed, deficit)."""
    if cache_tokens is None:
        cache_tokens = storage.get_cache_tokens(chat_id)
    billed = _billable_tokens(model, usage_in, usage_out, cache_tokens)
    billed = int(math.ceil(billed * settings.toki_spend_coeff))
    _spent_free, _spent_paid, deficit = storage.spend_tokens(user_id, billed)
    return billed, deficit



async def summarize_chat(chat_id: int, *, model: str, sentences: int = 4) -> ChatReply:
    msgs = storage.list_messages(chat_id, limit=40)
    parts: list[str] = []
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
    return ChatReply(
        text=_safe_trim(r.text, 700),
        usage_in=int(r.usage_in or 0),
        usage_out=int(r.usage_out or 0),
    )


async def _maybe_compress_history(user_id: int, chat_id: int, model: str) -> None:
    if not settings.limits.auto_compress_default:
        return
    msgs = storage.list_messages(chat_id)
    approx_tokens = sum(len(m["content"]) for m in msgs) // 4
    if approx_tokens <= int(settings.limits.context_threshold_tokens or 0):
        return
    summary = await summarize_chat(chat_id, model=model)
    storage.compress_history(
        chat_id,
        summary.text,
        usage_in=summary.usage_in,
        usage_out=summary.usage_out,
    )
    _apply_billing(user_id, chat_id, model, summary.usage_in, summary.usage_out)
    storage.add_cache_tokens(chat_id, summary.usage_out - summary.usage_in)


async def chat_turn(user_id: int, chat_id: int, text: str) -> ChatReply:
    user = storage.get_user(user_id) or {}
    ch = storage.get_chat(chat_id) or {}
    resp_size = (ch.get("resp_size") or "auto")
    toks_limit, char_limit = _size_caps(str(resp_size))
    model = (user.get("default_model") or settings.default_model)


    await _maybe_compress_history(user_id, chat_id, model)

    cache_before = storage.get_cache_tokens(chat_id)
    messages = await _collect_context(
        chat_id, user_id=user_id, model=model, query=text
    )
    messages += [dict(role="user", content=text)]
    r = await provider_chat(
        model=model,
        messages=messages,
        temperature=0.7,
        max_tokens=toks_limit,
        timeout_s=settings.limits.request_timeout_seconds,
    )
    out_text = _safe_trim(r.text, char_limit)

    usage_in = int(r.usage_in or 0)
    usage_out = int(r.usage_out or 0)
    billed, deficit = _apply_billing(
        user_id, chat_id, model, usage_in, usage_out, cache_before
    )
    storage.add_cache_tokens(chat_id, usage_in + usage_out)
    cost_in, cost_out, cost_cache, cost_total = calc_usage_cost_rub(
        model, usage_in, usage_out, cache_before
    )
    return ChatReply(
        text=out_text,
        usage_in=usage_in,
        usage_out=usage_out,
        billed=billed,
        deficit=deficit,
        cost_in=cost_in,
        cost_out=cost_out,
        cost_cache=cost_cache,
        cost_total=cost_total,
    )


async def live_stream(user_id: int, chat_id: int, text: str) -> AsyncGenerator[dict[str, str], None]:
    """
    Live-режим: отдаём сырые дельты текста + финальные usage.
    Хендлер агрегирует в буфер и нарезает на сообщения.
    """
    user = storage.get_user(user_id) or {}
    ch = storage.get_chat(chat_id) or {}
    resp_size = (ch.get("resp_size") or "auto")
    toks_limit, _ = _size_caps(str(resp_size))
    model = (user.get("default_model") or settings.default_model)


    await _maybe_compress_history(user_id, chat_id, model)

    cache_before = storage.get_cache_tokens(chat_id)
    messages = await _collect_context(
        chat_id, user_id=user_id, model=model, query=text
    )
    messages += [dict(role="user", content=text)]
    try:
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
                billed, deficit = _apply_billing(
                    user_id, chat_id, model, usage_in, usage_out, cache_before
                )
                storage.add_cache_tokens(chat_id, usage_in + usage_out)
                cost_in, cost_out, cost_cache, cost_total = calc_usage_cost_rub(
                    model, usage_in, usage_out, cache_before
                )

                yield {
                    "kind": "final",
                    "usage_in": str(usage_in),
                    "usage_out": str(usage_out),
                    "billed": str(billed),
                    "deficit": str(deficit),
                    "cost_in": f"{cost_in}",
                    "cost_out": f"{cost_out}",
                    "cost_cache": f"{cost_cache}",
                    "cost_total": f"{cost_total}",
                }
    except Exception:
        logger.exception("live_stream failed")
        storage.set_user_chatting(user_id, False)
        yield {
            "kind": "final",
            "text": "⚠ Что-то пошло не так. Попробуйте ещё раз.",
            "usage_in": "0",
            "usage_out": "0",
            "billed": "0",
            "deficit": "0",
            "cost_in": "0",
            "cost_out": "0",
            "cost_cache": "0",
            "cost_total": "0",
        }


async def chat_stream(user_id: int, chat_id: int, text: str):
    async for ev in live_stream(user_id, chat_id, text):
        yield ev

