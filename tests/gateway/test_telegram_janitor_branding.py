import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gateway.config import PlatformConfig
from gateway.platforms import telegram as telegram_module
from gateway.platforms.telegram import TelegramAdapter


def _make_adapter() -> TelegramAdapter:
    adapter = TelegramAdapter(PlatformConfig(enabled=True, token="***", extra={}))
    adapter._bot = AsyncMock()
    return adapter


@pytest.mark.asyncio
async def test_maybe_set_janitor_avatar_uploads_first_run(tmp_path, monkeypatch):
    avatar_path = tmp_path / "janitor_avatar.png"
    avatar_path.write_bytes(b"fake-png")
    monkeypatch.setattr(telegram_module, "_JANITOR_AVATAR_PATH", avatar_path, raising=False)
    monkeypatch.setattr(telegram_module, "get_hermes_home", lambda: tmp_path, raising=False)

    adapter = _make_adapter()

    await adapter._maybe_set_janitor_avatar()

    adapter._bot.set_my_profile_photo.assert_awaited_once()
    flag_path = tmp_path / "telegram_avatar_flag"
    assert flag_path.read_text() == str(avatar_path.stat().st_mtime)


@pytest.mark.asyncio
async def test_maybe_set_janitor_avatar_skips_when_mtime_matches(tmp_path, monkeypatch):
    avatar_path = tmp_path / "janitor_avatar.png"
    avatar_path.write_bytes(b"fake-png")
    flag_path = tmp_path / "telegram_avatar_flag"
    flag_path.write_text(str(avatar_path.stat().st_mtime))
    monkeypatch.setattr(telegram_module, "_JANITOR_AVATAR_PATH", avatar_path, raising=False)
    monkeypatch.setattr(telegram_module, "get_hermes_home", lambda: tmp_path, raising=False)

    adapter = _make_adapter()

    await adapter._maybe_set_janitor_avatar()

    adapter._bot.set_my_profile_photo.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_start_sends_janitor_welcome_photo(tmp_path, monkeypatch):
    welcome_path = tmp_path / "telegram_welcome.jpg"
    welcome_path.write_bytes(b"fake-jpg")
    monkeypatch.setattr(telegram_module, "_JANITOR_WELCOME_PATH", welcome_path, raising=False)

    adapter = _make_adapter()
    update = SimpleNamespace(effective_chat=SimpleNamespace(id=12345))

    await adapter._handle_start(update, SimpleNamespace())

    adapter._bot.send_photo.assert_awaited_once()
    _, kwargs = adapter._bot.send_photo.await_args
    assert kwargs["chat_id"] == 12345
    assert kwargs["caption"] == telegram_module._JANITOR_WELCOME_TEXT
    adapter._bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_start_falls_back_to_text_when_welcome_photo_missing(tmp_path, monkeypatch):
    missing_path = tmp_path / "missing.jpg"
    monkeypatch.setattr(telegram_module, "_JANITOR_WELCOME_PATH", missing_path, raising=False)

    adapter = _make_adapter()
    update = SimpleNamespace(effective_chat=SimpleNamespace(id=12345))

    await adapter._handle_start(update, SimpleNamespace())

    adapter._bot.send_photo.assert_not_awaited()
    adapter._bot.send_message.assert_awaited_once_with(
        chat_id=12345,
        text=telegram_module._JANITOR_WELCOME_TEXT,
    )
