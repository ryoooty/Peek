from __future__ import annotations

"""Helpers for calculating billable token usage."""

import math
from importlib import import_module


def _settings():
    """Lazy import of global settings to avoid circular imports."""
    return import_module("app.config").settings


def usage_to_toki(
    model: str,
    in_tokens: int,
    out_tokens: int,
    cached_tokens: int = 0,
) -> int:

    """Convert token usage to internal ``toki`` billing units.

    ``cached_tokens`` represents the previously billed total (input + output)
    for a chat. Only the difference between the current total and the cached
    value will be billed.

    Args:
        model: Identifier of the model used for the request.
        in_tokens: Number of input tokens consumed so far.
        out_tokens: Number of output tokens produced so far.
        cached_tokens: Previously billed total tokens for the chat.


    Returns:
        Number of billable ``toki`` units. Returns 0 if there is no new usage.
    """
    total = int(in_tokens) + int(out_tokens)
    delta = max(0, total - int(cached_tokens))
    if delta <= 0:
        return 0

    # Split the delta proportionally between input and output usage to preserve
    # their relative pricing.
    in_ratio = (in_tokens / total) if total else 0
    in_delta = int(round(delta * in_ratio))
    out_delta = delta - in_delta

    s = _settings()
    tariff = s.model_tariffs.get(model) or s.model_tariffs.get(s.default_model)
    effective_in = max(0, in_tokens - cached_tokens)
    if not tariff:
        return in_delta + out_delta
    units = (
        in_delta * tariff.input_per_1k + out_delta * tariff.output_per_1k

    ) / 1000.0
    return max(1, int(math.ceil(units)))
