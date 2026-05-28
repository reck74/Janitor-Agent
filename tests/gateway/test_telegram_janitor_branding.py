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


# ── _set_janitor_avatar  ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_set_janitor_avatar_always_uploads(tmp_path, monkeypatch):
    """Avatar must upload on every connect — no flag file gate."""
    avatar_path = tmp_path / "janitor_avatar.png"
    avatar_path.write_bytes(b"fake-png")
    monkeypatch.setattr(telegram_module, "_JANITOR_AVATAR_PATH", avatar_path, raising=False)

    adapter = _make_adapter()

    await adapter._set_janitor_avatar()

    adapter._bot.remove_my_profile_photo.assert_awaited_once()
    adapter._bot.set_my_profile_photo.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_janitor_avatar_skips_when_asset_missing(tmp_path, monkeypatch):
    """Missing avatar asset must not block startup."""
    missing = tmp_path / "nonexistent.png"
    monkeypatch.setattr(telegram_module, "_JANITOR_AVATAR_PATH", missing, raising=False)

    adapter = _make_adapter()

    await adapter._set_janitor_avatar()

    adapter._bot.remove_my_profile_photo.assert_not_awaited()
    adapter._bot.set_my_profile_photo.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_janitor_avatar_uses_photo_argument(tmp_path, monkeypatch):
    """InputProfilePhotoStatic constructor must use photo= not media=."""
    avatar_path = tmp_path / "janitor_avatar.png"
    avatar_path.write_bytes(b"fake-png")
    captured = {}

    class FakeInputProfilePhotoStatic:
        def __init__(self, photo):
            captured["photo"] = photo

    monkeypatch.setattr(telegram_module, "_JANITOR_AVATAR_PATH", avatar_path, raising=False)
    monkeypatch.setattr(telegram_module, "InputProfilePhotoStatic", FakeInputProfilePhotoStatic, raising=False)

    adapter = _make_adapter()

    await adapter._set_janitor_avatar()

    assert captured["photo"] == avatar_path
    adapter._bot.set_my_profile_photo.assert_awaited_once()
    _, kwargs = adapter._bot.set_my_profile_photo.await_args
    assert "profile_photo" in kwargs


# ── _handle_start  ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_start_sends_janitor_welcome_photo(tmp_path, monkeypatch):
    """The /start welcome includes topic invitation and image."""
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
    assert "/topic" in kwargs["caption"]
    adapter._bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_start_falls_back_to_text_when_welcome_photo_missing(tmp_path, monkeypatch):
    """When the welcome image is absent, /start falls back to text only."""
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
