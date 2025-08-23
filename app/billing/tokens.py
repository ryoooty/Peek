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

    ``cached_tokens`` is the amount of tokens already billed for this chat.
    When a request reuses part of the previous context we don't charge the
    full input price for those tokens again.  Instead they are billed at a
    separate ``cache`` rate defined by the model tariff.

    Billing steps:

    * ``effective_in`` – new input tokens beyond the cached total – is
      calculated as ``max(in_tokens - cached_tokens, 0)``.
    * ``delta`` – total new tokens (input + output) – is
      ``max(in_tokens + out_tokens - cached_tokens, 0)``.
    * The new input/output portions are ``effective_in`` and
      ``delta - effective_in`` respectively.
    * The final ``toki`` amount is computed from these portions using the
      tariff rates and adding a cache component
      ``cached_tokens * tariff.cache_per_1k``.

    Args:
        model: Identifier of the model used for the request.
        in_tokens: Number of input tokens consumed so far.
        out_tokens: Number of output tokens produced so far.
        cached_tokens: Previously billed total tokens for the chat.


    Returns:
        Number of billable ``toki`` units. Returns 0 if there is no new usage.
    """
    total = int(in_tokens) + int(out_tokens)
    cached_tokens = int(cached_tokens)
    delta = max(0, total - cached_tokens)
    if delta <= 0:
        return 0

    # Portion of new tokens that comes from the fresh input.
    effective_in = max(int(in_tokens) - cached_tokens, 0)
    in_delta = effective_in
    out_delta = delta - in_delta

    s = _settings()
    tariff = s.model_tariffs.get(model) or s.model_tariffs.get(s.default_model)
    if not tariff:
        return in_delta + out_delta

    units = (
        in_delta * float(tariff.input_per_1k)
        + out_delta * float(tariff.output_per_1k)
        + cached_tokens * float(tariff.cache_per_1k)
    ) / 1000.0
    return max(1, int(math.ceil(units)))
