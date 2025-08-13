import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

# Stub out app.config to avoid external dependencies
class Tariff:
    def __init__(self, input_per_1k: float, output_per_1k: float, cache_per_1k: float):
        self.input_per_1k = input_per_1k
        self.output_per_1k = output_per_1k
        self.cache_per_1k = cache_per_1k


class DummySettings:
    def __init__(self):
        self.default_model = "gpt-4o-mini"
        self.model_tariffs = {
            "gpt-4o-mini": Tariff(1.0, 1.0, 0.5),
            "gpt-4o": Tariff(2.0, 2.0, 1.0),
            "deepseek-chat": Tariff(0.6, 0.6, 0.3),
            "deepseek-reasoner": Tariff(1.2, 1.2, 0.6),
        }


config_module = types.ModuleType("config")
config_module.settings = DummySettings()
sys.modules.setdefault("app.config", config_module)

from app.billing.pricing import calc_usage_cost_rub


@pytest.mark.parametrize(
    "model,prompt,completion,cache,expected",
    [
        ("gpt-4o-mini", 1000, 500, 0, (1.0, 0.5, 0.0, 1.5)),
        ("gpt-4o", 2000, 1000, 0, (4.0, 2.0, 0.0, 6.0)),
        ("deepseek-chat", 500, 500, 500, (0.3, 0.3, 0.15, 0.75)),
        ("unknown-model", 1000, 1000, 0, (1.0, 1.0, 0.0, 2.0)),
    ],
)
def test_calc_usage_cost_rub(model, prompt, completion, cache, expected):
    cost = calc_usage_cost_rub(model, prompt, completion, cache)
    assert cost == pytest.approx(expected)
