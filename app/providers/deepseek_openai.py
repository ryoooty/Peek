from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List

from app.config import settings

try:
    import aiohttp  # type: ignore
except Exception:
    aiohttp = None  # type: ignore


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
        txt = messages[-1]["content"] if messages else ""
        return ChatResult(text=f"(fallback) {txt[:max_tokens]}")
    url = f"{settings.deepseek_base_url.rstrip('/')}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
    }
    payload = dict(
        model=model, messages=messages, temperature=temperature, max_tokens=max_tokens
    )
    timeout = aiohttp.ClientTimeout(total=timeout_s)
    async with aiohttp.ClientSession(timeout=timeout) as ses:
        async with ses.post(url, headers=headers, json=payload) as resp:
            data = await resp.json()
    try:
        choice = data["choices"][0]
        txt = choice["message"]["content"]
        usage = data.get("usage", {})
        return ChatResult(
            text=txt,
            usage_in=int(usage.get("prompt_tokens") or 0),
            usage_out=int(usage.get("completion_tokens") or 0),
        )
    except Exception:
        return ChatResult(text=json.dumps(data)[:max_tokens])


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
    timeout = aiohttp.ClientTimeout(total=timeout_s)

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
    except Exception:
        r = await chat(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
        )
        yield {"type": "delta", "text": r.text}
        yield {"type": "usage", "in": r.usage_in, "out": r.usage_out}
