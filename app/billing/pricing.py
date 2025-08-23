from __future__ import annotations

"""Utilities for working with pricing information."""
from importlib import import_module


def _settings():
    return import_module("app.config").settings


def get_out_price_per_1k(model: str) -> float:
    """Return price for 1k output tokens for given model."""
    s = _settings()
    t = s.model_tariffs.get(model) or s.model_tariffs.get(s.default_model)
    return float(t.output_per_1k if t else 0.0)


def calc_usage_cost_rub(
    model: str, in_tokens: int, out_tokens: int, cached_tokens: int = 0
) -> tuple[float, float, float, float]:
    """Calculate usage cost in rubles for given model.

    Args:
        model: Identifier of the model.
        in_tokens: Number of input tokens.
        out_tokens: Number of output tokens.
        cached_tokens: Number of cached tokens reused.

    Returns:
        Tuple ``(cost_in, cost_out, cost_cache, cost_total)`` where each value is
        expressed in rubles.
    """

    s = _settings()
    tariff = s.model_tariffs.get(model) or s.model_tariffs.get(s.default_model)
    if not tariff:
        return 0.0, 0.0, 0.0, 0.0

    cost_in = in_tokens * float(tariff.input_per_1k) / 1000.0
    cost_out = out_tokens * float(tariff.output_per_1k) / 1000.0
    cost_cache = cached_tokens * float(tariff.cache_per_1k) / 1000.0
    total = cost_in + cost_out + cost_cache
    return cost_in, cost_out, cost_cache, total


