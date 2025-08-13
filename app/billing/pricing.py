from __future__ import annotations
"""Utilities for translating token usage into actual cost in roubles."""

from typing import Tuple

from app.config import settings


def get_out_price_per_1k(model: str) -> float:
    """Return price for 1k output tokens for given model."""
    t = settings.model_tariffs.get(model) or settings.model_tariffs.get(
        settings.default_model
    )
    return float(t.output_per_1k if t else 0.0)


def calc_usage_cost_rub(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cache_tokens: int = 0,
) -> Tuple[float, float, float, float]:
    """Calculate usage cost for a model in roubles.

    Returns tuple ``(cost_in, cost_out, cost_cache, total)``. ``cache_tokens``
    corresponds to tokens served from cache (usually ``0``).
    """

    t = settings.model_tariffs.get(model) or settings.model_tariffs.get(
        settings.default_model
    )
    if not t:
        return 0.0, 0.0, 0.0, 0.0

    in_k = prompt_tokens / 1000.0
    out_k = completion_tokens / 1000.0
    cache_k = cache_tokens / 1000.0

    price_in = in_k * t.input_per_1k
    price_out = out_k * t.output_per_1k
    price_cache = cache_k * t.cache_per_1k
    total = round(price_in + price_out + price_cache, 4)

    return round(price_in, 4), round(price_out, 4), round(price_cache, 4), total
