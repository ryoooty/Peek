import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))


class Tariff:
    def __init__(self, input_per_1k: float = 1.0, output_per_1k: float = 1.0, cache_per_1k: float = 0.5):
        self.input_per_1k = input_per_1k
        self.output_per_1k = output_per_1k
        self.cache_per_1k = cache_per_1k


class DummySettings:
    def __init__(self):
        self.default_model = "model-a"
        self.model_tariffs = {
            "model-a": Tariff(input_per_1k=2.0, output_per_1k=3.0, cache_per_1k=1.0)
        }


pricing_module = importlib.import_module("app.billing.pricing")
importlib.reload(pricing_module)
pricing_module._settings = lambda: DummySettings()
calc_usage_cost_rub = pricing_module.calc_usage_cost_rub


def test_calc_usage_cost_rub_basic():
    cost_in, cost_out, cost_cache, total = calc_usage_cost_rub("model-a", 500, 1000, 200)
    assert cost_in == pytest.approx(1.0)
    assert cost_out == pytest.approx(3.0)
    assert cost_cache == pytest.approx(0.2)
    assert total == pytest.approx(4.2)


def test_calc_usage_cost_rub_fallback_to_default():
    cost_in, cost_out, cost_cache, total = calc_usage_cost_rub("unknown", 100, 50, 0)
    assert cost_in == pytest.approx(0.2)
    assert cost_out == pytest.approx(0.15)
    assert cost_cache == pytest.approx(0.0)
    assert total == pytest.approx(0.35)
