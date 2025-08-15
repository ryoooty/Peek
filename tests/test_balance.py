import sys
import types
import asyncio
from pathlib import Path

import asyncio
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))


class Tariff:
    def __init__(self, input_per_1k: float, output_per_1k: float, cache_per_1k: float):
        self.input_per_1k = input_per_1k
        self.output_per_1k = output_per_1k
        self.cache_per_1k = cache_per_1k


class DummyLimits:
    context_threshold_tokens = 0
    auto_compress_default = False
    request_timeout_seconds = 60


class DummySettings:
    def __init__(self):
        self.default_model = "gpt-4o-mini"
        self.model_tariffs = {
            "gpt-4o-mini": Tariff(1.0, 1.0, 0.5),
            "gpt-4o": Tariff(2.0, 2.0, 1.0),
            "deepseek-chat": Tariff(0.6, 0.6, 0.3),
            "deepseek-reasoner": Tariff(1.2, 1.2, 0.6),
        }
        self.limits = DummyLimits()
        self.deepseek_base_url = ""
        self.deepseek_api_key = None
        self.toki_spend_coeff = 1.0


config_module = types.ModuleType("config")
config_module.settings = DummySettings()
config_module.BASE_DIR = ROOT
config_module.register_reload_hook = lambda fn: None
sys.modules["app.config"] = config_module

from app import storage
from app.handlers.balance import cb_open_balance, cmd_balance


class DummyMessage:
    def __init__(self, user_id: int, username: str | None = None):
        self.from_user = types.SimpleNamespace(id=user_id, username=username)
        self.sent: list[str] = []

    async def answer(self, text: str):
        self.sent.append(text)


class DummyCall:
    def __init__(self, user_id: int):
        self.from_user = types.SimpleNamespace(id=user_id)
        self.message = DummyMessage(user_id)

    async def answer(self, *args, **kwargs):
        pass


def test_cb_open_balance_sends_new_message(tmp_path):
    storage.init(tmp_path / "db.sqlite")
    storage.ensure_user(1, "test")
    call = DummyCall(1)

    asyncio.run(cb_open_balance(call))
    assert call.message.sent and "Баланс" in call.message.sent[0]
    assert "Кэш‑токены" not in call.message.sent[0]


def test_cmd_balance_sends_new_message(tmp_path):
    storage.init(tmp_path / "db2.sqlite")
    storage.ensure_user(2, "test2")
    msg = DummyMessage(2)

    asyncio.run(cmd_balance(msg))
    assert msg.sent and "Баланс" in msg.sent[0]
    assert "Кэш‑токены" not in msg.sent[0]


