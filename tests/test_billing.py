import sys
import types
import pytest
from types import SimpleNamespace

# Create stub settings module before importing pricing
settings = SimpleNamespace()
config_module = types.ModuleType('app.config')
config_module.settings = settings
sys.modules.setdefault('app.config', config_module)

from app.billing.pricing import get_out_price_per_1k, calc_user_price_rub


@pytest.fixture(autouse=True)
def pricing_setup():
    settings.pricing = SimpleNamespace(
        deepseek_reasoner=SimpleNamespace(out=2.0, in_miss=1.0),
        deepseek_chat=SimpleNamespace(out=1.0, in_miss=0.5),
    )
    yield


def test_get_out_price_per_1k():
    assert get_out_price_per_1k('deepseek-reasoner') == 2.0
    assert get_out_price_per_1k('deepseek-chat') == 1.0
    assert get_out_price_per_1k('unknown') == 1.0


def test_calc_user_price_rub():
    price_in, price_out, total = calc_user_price_rub('deepseek-reasoner', 1000, 2000)
    assert (price_in, price_out, total) == (1.0, 4.0, 5.0)


def test_calc_user_price_rub_unknown_model():
    price_in, price_out, total = calc_user_price_rub('unknown', 500, 500)
    assert (price_in, price_out, total) == (0.25, 0.5, 0.75)
