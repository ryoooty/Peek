import importlib
from types import SimpleNamespace

class Tariff:
    def __init__(self, input_per_1k=1.0, output_per_1k=2.0, cache_per_1k=0.5):
        self.input_per_1k = input_per_1k
        self.output_per_1k = output_per_1k
        self.cache_per_1k = cache_per_1k

class DummySettings:
    def __init__(self):
        self.default_model = "m"
        self.model_tariffs = {"m": Tariff()}


tokens_module = importlib.import_module("app.billing.tokens")
importlib.reload(tokens_module)
tokens_module._settings = lambda: DummySettings()
usage_to_toki = tokens_module.usage_to_toki


def test_usage_to_toki_includes_cache_component():
    # effective_in = 1200 - 1000 = 200
    # delta = (1200 + 800) - 1000 = 1000 => out_delta = 800
    # units = (200*1 + 800*2 + 1000*0.5)/1000 = 2.3 -> ceil -> 3
    assert usage_to_toki("m", 1200, 800, 1000) == 3
