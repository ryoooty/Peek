from __future__ import annotations

"""Helpers for calculating billable token usage."""

import math
from importlib import import_module


def _settings():
    """Lazy import of global settings to avoid circular imports."""
    return import_module("app.config").settings


def usage_to_toki(model, in_tokens, out_tokens, cached_tokens=0):
    """Convert token usage to internal ``toki`` billing units.

    Args:
        model: Identifier of the model used for the request.
        in_tokens: Number of input tokens consumed.
        out_tokens: Number of output tokens produced.
        cached_tokens: Number of cached input tokens.

    Returns:
        Number of billable ``toki`` units. At least one unit is always
        charged even for zero usage.
    """
    s = _settings()
    tariff = s.model_tariffs.get(model) or s.model_tariffs.get(s.default_model)
    effective_in = max(0, in_tokens - cached_tokens)
    if not tariff:
        return effective_in + out_tokens + cached_tokens
    units = (
        effective_in * tariff.input_per_1k
        + out_tokens * tariff.output_per_1k
        + cached_tokens * tariff.cache_per_1k
    ) / 1000.0
    return max(1, int(math.ceil(units)))
