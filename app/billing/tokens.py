from __future__ import annotations

"""Utilities for converting token usage to billable ``toki`` units."""

import math

from app.config import settings


def usage_to_toki(
    model: str,
    in_tokens: int,
    out_tokens: int,
    cache_tokens: int = 0,
) -> int:
    """Translate raw token usage into billable ``toki`` units.

    Parameters
    ----------
    model:
        Name of the model whose tariff should be used. Falls back to
        ``settings.default_model`` if the specific model is not configured.
    in_tokens:
        Number of prompt (input) tokens consumed.
    out_tokens:
        Number of completion (output) tokens produced.
    cache_tokens:
        Tokens served from cache.  Defaults to ``0``.

    Returns
    -------
    int
        Billable ``toki`` units.  At least ``1`` unit is always billed for any
        non-zero usage.  If no tariff is configured for the model, the function
        falls back to simply summing the provided token counts.
    """

    tariff = settings.model_tariffs.get(model) or settings.model_tariffs.get(
        settings.default_model
    )
    if not tariff:
        return in_tokens + out_tokens + cache_tokens

    units = (
        in_tokens * tariff.input_per_1k
        + out_tokens * tariff.output_per_1k
        + cache_tokens * tariff.cache_per_1k
    ) / 1000.0
    return max(1, int(math.ceil(units)))
