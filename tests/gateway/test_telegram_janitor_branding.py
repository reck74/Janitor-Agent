import sys
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

# pyright: reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportPrivateUsage=false, reportOptionalMemberAccess=false

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
    avatar_path = tmp_path / "janitor_avatar_telegram.jpg"
    avatar_path.write_bytes(b"fake-jpg")
    monkeypatch.setattr(telegram_module, "_JANITOR_TELEGRAM_AVATAR_PATH", avatar_path, raising=False)

    adapter = _make_adapter()

    await adapter._set_janitor_avatar()

    adapter._bot.remove_my_profile_photo.assert_awaited_once()
    adapter._bot.set_my_profile_photo.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_janitor_avatar_skips_when_asset_missing(tmp_path, monkeypatch):
    """Missing avatar asset must not block startup."""
    missing = tmp_path / "nonexistent.jpg"
    monkeypatch.setattr(telegram_module, "_JANITOR_TELEGRAM_AVATAR_PATH", missing, raising=False)

    adapter = _make_adapter()

    await adapter._set_janitor_avatar()

    adapter._bot.remove_my_profile_photo.assert_not_awaited()
    adapter._bot.set_my_profile_photo.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_janitor_avatar_uses_photo_argument(tmp_path, monkeypatch):
    """InputProfilePhotoStatic constructor must use photo= not media=."""
    avatar_path = tmp_path / "janitor_avatar_telegram.jpg"
    avatar_path.write_bytes(b"fake-jpg")
    captured = {}

    class FakeInputProfilePhotoStatic:
        def __init__(self, photo):
            captured["photo"] = photo

    monkeypatch.setattr(telegram_module, "_JANITOR_TELEGRAM_AVATAR_PATH", avatar_path, raising=False)
    monkeypatch.setattr(telegram_module, "InputProfilePhotoStatic", FakeInputProfilePhotoStatic, raising=False)

    adapter = _make_adapter()

    await adapter._set_janitor_avatar()

    assert captured["photo"] == avatar_path
    adapter._bot.set_my_profile_photo.assert_awaited_once()
    _, kwargs = adapter._bot.set_my_profile_photo.await_args
    assert kwargs["photo"] is not None
    assert "profile_photo" not in kwargs


@pytest.mark.asyncio
async def test_set_janitor_avatar_fallback_uses_photo_kwarg(tmp_path, monkeypatch):
    """Fallback upload path must still use photo=, not profile_photo=."""
    avatar_path = tmp_path / "janitor_avatar_telegram.jpg"
    avatar_path.write_bytes(b"fake-jpg")
    monkeypatch.setattr(telegram_module, "_JANITOR_TELEGRAM_AVATAR_PATH", avatar_path, raising=False)
    monkeypatch.setattr(telegram_module, "InputProfilePhotoStatic", None, raising=False)

    adapter = _make_adapter()

    await adapter._set_janitor_avatar()

    adapter._bot.set_my_profile_photo.assert_awaited_once()
    _, kwargs = adapter._bot.set_my_profile_photo.await_args
    assert "photo" in kwargs
    assert "profile_photo" not in kwargs


@pytest.mark.asyncio
async def test_set_janitor_avatar_warns_when_ptb_too_old(tmp_path, monkeypatch):
    """Old PTB should warn about 22.7 and skip avatar upload."""
    avatar_path = tmp_path / "janitor_avatar_telegram.jpg"
    avatar_path.write_bytes(b"fake-jpg")
    monkeypatch.setattr(telegram_module, "_JANITOR_TELEGRAM_AVATAR_PATH", avatar_path, raising=False)
    warning = Mock()
    monkeypatch.setattr(telegram_module.logger, "warning", warning)

    adapter = _make_adapter()
    adapter._bot = SimpleNamespace()

    await adapter._set_janitor_avatar()

    assert warning.called
    assert "22.7" in warning.call_args.args[0]


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


def test_telegram_avatar_asset_is_jpeg():
    asset = ROOT / "assets/janitor/janitor_avatar_telegram.jpg"

    assert asset.exists()
    assert asset.read_bytes()[:3] == b"\xff\xd8\xff"

    result = subprocess.run(["file", str(asset)], capture_output=True, text=True, check=True)
    assert "JPEG image data" in result.stdout
