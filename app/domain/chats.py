
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import AsyncGenerator

from app import storage
from app.billing.tokens import usage_to_toki
from app.billing.pricing import calc_usage_cost_rub
from app.config import settings
from app.providers.deepseek_openai import (
    chat as provider_chat,
    stream_chat as provider_stream,
)


logger = logging.getLogger(__name__)

DEFAULT_TOKENS_LIMIT = 700
DEFAULT_CHAR_LIMIT = 900


def _size_caps(resp_size: str) -> tuple[int, int]:
    """Return token/char caps for a given ``resp_size`` value.

    ``resp_size`` can be one of predefined aliases (e.g. ``"short"``,
    ``"long"``) or a string with explicit numbers like ``"500:800"`` where
    the first value denotes the token limit and the second one – character
    limit.  Unknown or malformed values fall back to the default limits.
    """

    if not resp_size:
        return DEFAULT_TOKENS_LIMIT, DEFAULT_CHAR_LIMIT

    rs = resp_size.strip().lower()

    # Predefined presets.  The exact numbers are not critical for the
    # application logic; they merely provide a few handy shortcuts while
    # keeping defaults as a safe fallback.
    presets: dict[str, tuple[int, int]] = {
        "auto": (DEFAULT_TOKENS_LIMIT, DEFAULT_CHAR_LIMIT),
        "default": (DEFAULT_TOKENS_LIMIT, DEFAULT_CHAR_LIMIT),
        "short": (350, 500),
        "medium": (DEFAULT_TOKENS_LIMIT, DEFAULT_CHAR_LIMIT),
        "long": (1000, 1500),
        "xs": (200, 300),
        "s": (350, 500),
        "m": (DEFAULT_TOKENS_LIMIT, DEFAULT_CHAR_LIMIT),
        "l": (1000, 1500),
        "xl": (1500, 2000),
    }

    if rs in presets:
        return presets[rs]

    # Attempt to parse explicit numeric values. Supported separators: ``:``,
    # ``/`` and ``,``.  If only a single number is provided we interpret it as
    # the token limit and keep the character limit at default.
    for sep in (":", "/", ",", "x", " "):
        if sep in rs:
            tok_s, char_s = rs.split(sep, 1)
            try:
                toks = int(tok_s)
            except ValueError:
                toks = DEFAULT_TOKENS_LIMIT
            try:
                chars = int(char_s)
            except ValueError:
                chars = DEFAULT_CHAR_LIMIT
            return toks, chars

    try:
        toks = int(rs)
        return toks, DEFAULT_CHAR_LIMIT
    except ValueError:
        return DEFAULT_TOKENS_LIMIT, DEFAULT_CHAR_LIMIT

@dataclass
class ChatReply:
    text: str
    usage_in: int = 0
    usage_out: int = 0
    billed: int = 0
    deficit: int = 0


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
        _apply_billing(
            user_id,
            chat_id,
            model,
            summary.usage_in,
            summary.usage_out,
            cached_tokens=0,
        )

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
def _apply_billing(
    user_id: int,
    chat_id: int,
    model: str,
    usage_in: int,
    usage_out: int,
    *,

    cached_tokens: int = 0,
) -> tuple[int, int]:
    """Возвращает (billed, deficit)."""
    billed = usage_to_toki(model, usage_in, usage_out, cached_tokens)
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
    _apply_billing(
        user_id,
        chat_id,
        model,
        summary.usage_in,
        summary.usage_out,
        cached_tokens=0,
    )


async def chat_turn(user_id: int, chat_id: int, text: str) -> ChatReply:
    user = storage.get_user(user_id) or {}
    storage.get_chat(chat_id)  # ensure chat exists
    cached_tokens = storage.get_cached_tokens(chat_id)
    toks_limit, char_limit = DEFAULT_TOKENS_LIMIT, DEFAULT_CHAR_LIMIT
    model = (user.get("default_model") or settings.default_model)

    balance = int(user.get("free_toki") or 0) + int(user.get("paid_tokens") or 0)
    if balance <= 0:
        return ChatReply(
            text="⚠ Баланс токенов на нуле. Пополните баланс, чтобы продолжить комфортно.",
            deficit=1,
        )

    await _maybe_compress_history(user_id, chat_id, model)


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
        user_id, chat_id, model, usage_in, usage_out, cached_tokens=cached_tokens
    )
    if deficit > 0:
        return ChatReply(
            text="⚠ Баланс токенов на нуле. Пополните баланс, чтобы продолжить комфортно.",
            usage_in=usage_in,
            usage_out=usage_out,
            billed=billed,
            deficit=deficit,
        )

    storage.set_cached_tokens(chat_id, usage_in + usage_out)

    return ChatReply(
        text=out_text,
        usage_in=usage_in,
        usage_out=usage_out,
        billed=billed,
        deficit=deficit,
    )



async def live_stream(user_id: int, chat_id: int, text: str) -> AsyncGenerator[dict[str, str], None]:
    """
    Live-режим: отдаём сырые дельты текста + финальные usage.
    Хендлер агрегирует в буфер и нарезает на сообщения.
    """
    user = storage.get_user(user_id) or {}
    ch = storage.get_chat(chat_id) or {}
    cached_tokens = storage.get_cached_tokens(chat_id)
    resp_size = (ch.get("resp_size") or "auto")
    toks_limit, _ = _size_caps(str(resp_size))
    model = (user.get("default_model") or settings.default_model)

    balance = int(user.get("free_toki") or 0) + int(user.get("paid_tokens") or 0)
    if balance <= 0:
        yield {
            "kind": "final",
            "text": "⚠ Баланс токенов на нуле. Пополните баланс, чтобы продолжить комфортно.",
            "usage_in": "0",
            "usage_out": "0",
            "billed": "0",
            "deficit": "1",
        }
        return

    await _maybe_compress_history(user_id, chat_id, model)


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
                    user_id,
                    chat_id,
                    model,
                    usage_in,
                    usage_out,
                    cached_tokens=cached_tokens,
                )
                if deficit > 0:
                    yield {
                        "kind": "final",
                        "text": "⚠ Баланс токенов на нуле. Пополните баланс, чтобы продолжить комфортно.",
                        "usage_in": str(usage_in),
                        "usage_out": str(usage_out),
                        "billed": str(billed),
                        "deficit": str(deficit),
                    }
                else:
                    storage.set_cached_tokens(chat_id, usage_in + usage_out)
                    yield {
                        "kind": "final",
                        "usage_in": str(usage_in),
                        "usage_out": str(usage_out),
                        "billed": str(billed),
                        "deficit": str(deficit),
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
        }


async def chat_stream(user_id: int, chat_id: int, text: str):
    async for ev in live_stream(user_id, chat_id, text):
        yield ev


