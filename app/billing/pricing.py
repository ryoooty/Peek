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


