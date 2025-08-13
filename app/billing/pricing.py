from __future__ import annotations
from typing import Tuple
from app.config import settings


def calc_usage_cost(
    model: str,
    usage_in: int,
    usage_out: int,
    cache_tokens: int = 0,
) -> Tuple[float, float, float, float]:
    """Return cost for the given token usage.

    Costs are calculated in "billing" units according to settings.model_tariffs.
    Returns tuple of (input_cost, output_cost, cache_cost, total_cost).
    """

    t = settings.model_tariffs.get(model) or settings.model_tariffs.get(settings.default_model)
    if not t:
        return 0.0, 0.0, 0.0, 0.0

    price_in = (usage_in * t.input_per_1k) / 1000.0
    price_out = (usage_out * t.output_per_1k) / 1000.0
    price_cache = (cache_tokens * t.cache_per_1k) / 1000.0

    total = round(price_in + price_out + price_cache, 4)
    return round(price_in, 4), round(price_out, 4), round(price_cache, 4), total
