import sys
import types
import asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

# Stub config with BASE_DIR for import
config_module = types.ModuleType("config")
config_module.BASE_DIR = ROOT
config_module.settings = types.SimpleNamespace()
sys.modules["app.config"] = config_module

from app import storage
import app.handlers.characters as characters

# Clean up stub so it doesn't affect other tests
del sys.modules["app.config"]


class DummyMessage:
    def __init__(self):
        self.from_user = types.SimpleNamespace(id=1)
        self.photo_sent = []

    async def answer_photo(self, photo, caption=None, reply_markup=None):
        self.photo_sent.append(photo)

    async def answer(self, text, reply_markup=None):
        pass


def test_open_character_card_sends_photo_by_id(tmp_path, monkeypatch):
    storage.init(tmp_path / "db.sqlite")
    char_id = storage.ensure_character(name="Test", photo_id="file123")

    msg = DummyMessage()
    monkeypatch.setattr(characters, "BASE_DIR", tmp_path)

    asyncio.run(characters.open_character_card(msg, char_id=char_id))

    assert msg.photo_sent == ["file123"]
