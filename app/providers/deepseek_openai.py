from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List

from app.config import settings

try:
    import aiohttp  # type: ignore
except Exception:  # pragma: no cover - aiohttp may be missing in tests
    aiohttp = None  # type: ignore


logger = logging.getLogger(__name__)
FALLBACK_TEXT = "⚠️ Сервис временно недоступен, попробуйте позже"


@dataclass
class ChatResult:
    text: str
    usage_in: int = 0
    usage_out: int = 0


async def chat(
    *,
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 512,
    timeout_s: int = 60,
) -> ChatResult:
    if aiohttp is None:
        return ChatResult(text=FALLBACK_TEXT)

    url = f"{settings.deepseek_base_url.rstrip('/')}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
    }
    payload = dict(
        model=model, messages=messages, temperature=temperature, max_tokens=max_tokens
    )
    timeout = aiohttp.ClientTimeout(connect=timeout_s, sock_read=timeout_s)
    attempts = max(1, int(getattr(settings.limits, "request_attempts", 1)))
    for attempt in range(1, attempts + 1):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as ses:
                async with ses.post(url, headers=headers, json=payload) as resp:
                    data = await resp.json()
            choice = data["choices"][0]
            txt = choice["message"]["content"]
            usage = data.get("usage", {})
            return ChatResult(
                text=txt,
                usage_in=int(usage.get("prompt_tokens") or 0),
                usage_out=int(usage.get("completion_tokens") or 0),
            )
        except Exception:
            if attempt >= attempts:
                logger.exception("deepseek chat failed")
                break
            await asyncio.sleep(2 ** (attempt - 1))
    return ChatResult(text=FALLBACK_TEXT)


async def stream_chat(
    *,
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 512,
    timeout_s: int = 60,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    SSE-стрим. Генерирует словари:
      {"type":"delta","text": "<piece>"}  — когда пришёл кусок текста
      {"type":"usage","in": prompt_tokens, "out": completion_tokens} — финальная мета
    Фолбэк: если стрим недоступен — даёт один delta и usage (нулевой).
    """
    if aiohttp is None:
        r = await chat(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
        )
        yield {"type": "delta", "text": r.text}
        yield {"type": "usage", "in": r.usage_in, "out": r.usage_out}
        return

    url = f"{settings.deepseek_base_url.rstrip('/')}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
    }
    payload = dict(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )
    timeout = aiohttp.ClientTimeout(connect=timeout_s, sock_read=timeout_s)
    attempts = max(1, int(getattr(settings.limits, "request_attempts", 1)))

    for attempt in range(1, attempts + 1):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as ses:
                async with ses.post(url, headers=headers, json=payload) as resp:
                    async for line in resp.content:
                        if not line or line == b"\n":
                            continue
                        if not line.startswith(b"data:"):
                            continue
                        chunk = line[len(b"data:") :].strip()
                        if chunk == b"[DONE]":
                            break
                        try:
                            data = json.loads(chunk)
                            if "usage" in data:
                                u = data["usage"]
                                yield {
                                    "type": "usage",
                                    "in": int(u.get("prompt_tokens") or 0),
                                    "out": int(u.get("completion_tokens") or 0),
                                }
                                continue
                            delta = data["choices"][0]["delta"]
                            part = delta.get("content")
                            if part:
                                yield {"type": "delta", "text": part}
                        except Exception:
                            continue
            return
        except Exception:
            if attempt >= attempts:
                logger.exception("deepseek stream_chat failed")
                break
            await asyncio.sleep(2 ** (attempt - 1))

    r = await chat(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_s=timeout_s,
    )
    yield {"type": "delta", "text": r.text}
    yield {"type": "usage", "in": r.usage_in, "out": r.usage_out}
