import sys
import types
import asyncio
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

# Stub config to avoid real settings
config_module = types.ModuleType("config")
config_module.BASE_DIR = ROOT

class DummySettings:
    def __init__(self):
        self.admin_ids = [1]

config_module.settings = DummySettings()
sys.modules["app.config"] = config_module

from app import storage
import app.handlers.admin as admin

del sys.modules["app.config"]


class DummyFile:
    def __init__(self, file_id: str):
        self.file_id = file_id
        self.file_path = "photo.jpg"


class DummyBot:
    async def get_file(self, file_id: str):
        return DummyFile(file_id)

    async def download(self, file: str | DummyFile, destination: Path):
        Path(destination).write_bytes(b"data")


class DummyMessage:
    def __init__(self):
        self.from_user = types.SimpleNamespace(id=1)
        self.text = "/char_photo 1"
        self.caption = None
        self.photo = [types.SimpleNamespace(file_id="file123")]
        self.reply_to_message = None
        self.bot = DummyBot()
        self.sent: list[str] = []

    async def answer(self, text: str):
        self.sent.append(text)


def test_cmd_char_photo_sends_single_confirmation(tmp_path, monkeypatch):
    storage.init(tmp_path / "db.sqlite")
    monkeypatch.setattr(admin, "MEDIA_DIR", tmp_path)
    msg = DummyMessage()
    asyncio.run(admin.cmd_char_photo(msg))
    assert len(msg.sent) == 1
    assert msg.sent[0].startswith("Фото сохранено")
