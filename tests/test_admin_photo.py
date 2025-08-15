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
import app.handlers.characters as characters

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
    def __init__(self, text: str, *, photo=None, caption=None):
        self.from_user = types.SimpleNamespace(id=1)
        self.text = text
        self.caption = caption
        self.photo = photo
        self.reply_to_message = None
        self.bot = DummyBot()
        self.sent: list[str] = []

    async def answer(self, text: str):
        self.sent.append(text)


def test_char_photo_requires_existing_character(tmp_path, monkeypatch):
    storage.init(tmp_path / "db.sqlite")
    monkeypatch.setattr(admin, "MEDIA_DIR", tmp_path)
    msg = DummyMessage("/char_photo 1", photo=[types.SimpleNamespace(file_id="f1")])
    asyncio.run(admin.cmd_char_photo(msg))
    assert msg.sent == ["Персонаж не найден. Сначала создайте его через /char_add"]


def test_char_add_photo_and_open(tmp_path, monkeypatch):
    storage.init(tmp_path / "db.sqlite")
    monkeypatch.setattr(admin, "MEDIA_DIR", tmp_path)

    # Add character
    msg_add = DummyMessage("/char_add TestName|test-slug|Fandom|Short info")
    sys.modules["app.config"] = config_module
    asyncio.run(admin.cmd_char_add(msg_add))
    del sys.modules["app.config"]
    assert msg_add.sent == ["Персонаж создан: id=1"]

    # Attach photo
    msg_photo = DummyMessage(
        "/char_photo 1", photo=[types.SimpleNamespace(file_id="file123")]
    )
    asyncio.run(admin.cmd_char_photo(msg_photo))
    assert msg_photo.sent and msg_photo.sent[0].startswith("Фото сохранено")

    ch = storage.get_character(1)

    # Open character card and ensure photo is used
    class FSInputFileDummy:
        def __init__(self, path: str):
            self.path = path

    captured: dict = {}

    async def fake_edit_or_send(message_or_call, *, media, caption, kb):
        captured["media"] = media
        captured["caption"] = caption

    monkeypatch.setattr(characters, "FSInputFile", FSInputFileDummy)
    monkeypatch.setattr(characters, "_edit_or_send_card", fake_edit_or_send)

    msg_open = DummyMessage("/open")
    asyncio.run(characters.open_character_card(msg_open, char_id=1))

    assert isinstance(captured.get("media"), FSInputFileDummy)
    assert captured["media"].path == ch["photo_path"]
