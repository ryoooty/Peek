from __future__ import annotations
from typing import Tuple
from app.config import settings


def get_out_price_per_1k(model: str) -> float:
    """Return output price per 1k tokens for a given model."""
    tariffs = settings.model_tariffs
    m = tariffs.get(model) or tariffs.get(settings.default_model)
    return m.output_per_1k if m else 0.0


def calc_user_price_rub(
    model: str, prompt_tokens: int, completion_tokens: int
) -> Tuple[float, float, float]:
    """Calculate input, output and total price in RUB for a request."""
    tariffs = settings.model_tariffs
    m = tariffs.get(model) or tariffs.get(settings.default_model)
    if m is None:
        return 0.0, 0.0, 0.0
    in_k = prompt_tokens / 1000.0
    out_k = completion_tokens / 1000.0
    price_in = in_k * m.input_per_1k
    price_out = out_k * m.output_per_1k
    total = round(price_in + price_out, 4)
    return round(price_in, 4), round(price_out, 4), total
