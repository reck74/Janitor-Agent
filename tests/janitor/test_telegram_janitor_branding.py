"""Janitor Telegram branding, delivered by the ``janitor`` plugin.

The upstream Telegram adapter is untouched; the ``/start`` welcome and the
bot avatar come from ``janitor.plugin.telegram`` through the
``pre_gateway_dispatch`` hook. These tests drive the hook against a real
``TelegramAdapter`` (only the PTB bot is faked) and load the plugin through
the real entry-point discovery path.
"""

import asyncio
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import yaml

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource
from janitor.plugin import telegram as branding
from plugins.platforms.telegram.adapter import TelegramAdapter

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _fresh_branding_state():
    branding._avatar_synced.clear()
    yield
    branding._avatar_synced.clear()


def _adapter() -> TelegramAdapter:
    adapter = TelegramAdapter(PlatformConfig(enabled=True, token="***", extra={}))
    adapter._bot = AsyncMock()
    return adapter


def _event(text: str, platform: Platform = Platform.TELEGRAM, chat_id: str = "12345") -> MessageEvent:
    return MessageEvent(text=text, source=SessionSource(platform=platform, chat_id=chat_id, user_id="7"))


async def _drain():
    while branding._background_tasks:
        await asyncio.gather(*list(branding._background_tasks), return_exceptions=True)


# ── /start welcome ────────────────────────────────────────────────────


@pytest.mark.parametrize("text", ["/start", "/start@JanitorBot", "/start deep-link", "  /START  "])
def test_start_variants_are_recognized(text):
    assert branding.is_start_command(text)


@pytest.mark.parametrize("text", ["", None, "start", "/startup", "hola /start", "/stop"])
def test_non_start_text_is_ignored(text):
    assert not branding.is_start_command(text)


@pytest.mark.asyncio
async def test_start_sends_welcome_photo_and_skips_dispatch(tmp_path, monkeypatch):
    welcome = tmp_path / "telegram_welcome.jpg"
    welcome.write_bytes(b"\xff\xd8\xff fake")
    monkeypatch.setattr(branding, "WELCOME_IMAGE_PATH", welcome)
    monkeypatch.setattr(branding, "AVATAR_PATH", tmp_path / "missing.jpg")
    adapter = _adapter()
    gateway = SimpleNamespace(adapters={Platform.TELEGRAM: adapter})

    result = branding.pre_gateway_dispatch(event=_event("/start"), gateway=gateway, session_store=None)
    await _drain()

    assert result == {"action": "skip", "reason": "janitor-telegram-welcome"}
    adapter._bot.send_photo.assert_awaited_once()
    kwargs = adapter._bot.send_photo.await_args.kwargs
    assert str(kwargs["chat_id"]) == "12345"
    assert kwargs["caption"] == branding.WELCOME_TEXT
    assert "/topic" in kwargs["caption"]


@pytest.mark.asyncio
async def test_start_falls_back_to_text_without_image(tmp_path, monkeypatch):
    monkeypatch.setattr(branding, "WELCOME_IMAGE_PATH", tmp_path / "missing.jpg")
    monkeypatch.setattr(branding, "AVATAR_PATH", tmp_path / "missing.jpg")
    adapter = _adapter()
    gateway = SimpleNamespace(adapters={Platform.TELEGRAM: adapter})

    result = branding.pre_gateway_dispatch(event=_event("/start"), gateway=gateway)
    await _drain()

    assert result["action"] == "skip"
    adapter._bot.send_photo.assert_not_awaited()
    adapter._bot.send_message.assert_awaited()
    assert "Soy The Janitor" in adapter._bot.send_message.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_regular_text_and_other_platforms_pass_through(tmp_path, monkeypatch):
    monkeypatch.setattr(branding, "AVATAR_PATH", tmp_path / "missing.jpg")
    adapter = _adapter()
    gateway = SimpleNamespace(adapters={Platform.TELEGRAM: adapter, Platform.DISCORD: adapter})

    assert branding.pre_gateway_dispatch(event=_event("hola"), gateway=gateway) is None
    assert branding.pre_gateway_dispatch(event=_event("/start", Platform.DISCORD), gateway=gateway) is None
    await _drain()
    adapter._bot.send_photo.assert_not_awaited()
    adapter._bot.send_message.assert_not_awaited()


def test_start_without_running_loop_is_not_swallowed():
    """Outside an event loop the welcome can't be sent, so dispatch continues."""
    gateway = SimpleNamespace(adapters={Platform.TELEGRAM: _adapter()})
    assert branding.pre_gateway_dispatch(event=_event("/start"), gateway=gateway) is None


@pytest.mark.asyncio
async def test_multiplexed_profile_adapter_is_used(tmp_path, monkeypatch):
    monkeypatch.setattr(branding, "WELCOME_IMAGE_PATH", tmp_path / "missing.jpg")
    monkeypatch.setattr(branding, "AVATAR_PATH", tmp_path / "missing.jpg")
    default, coder = _adapter(), _adapter()
    gateway = SimpleNamespace(
        adapters={Platform.TELEGRAM: default},
        _profile_adapters={"coder": {Platform.TELEGRAM: coder}},
    )
    event = MessageEvent(
        text="/start",
        source=SessionSource(platform=Platform.TELEGRAM, chat_id="1", user_id="7", profile="coder"),
    )

    branding.pre_gateway_dispatch(event=event, gateway=gateway)
    await _drain()

    coder._bot.send_message.assert_awaited()
    default._bot.send_message.assert_not_awaited()


# ── avatar ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_avatar_synced_once_per_adapter(tmp_path, monkeypatch):
    avatar = tmp_path / "janitor_avatar_telegram.jpg"
    avatar.write_bytes(b"\xff\xd8\xff fake")
    monkeypatch.setattr(branding, "AVATAR_PATH", avatar)
    adapter = _adapter()
    gateway = SimpleNamespace(adapters={Platform.TELEGRAM: adapter})

    for text in ("hola", "otra", "/help"):
        branding.pre_gateway_dispatch(event=_event(text), gateway=gateway)
    await _drain()

    adapter._bot.remove_my_profile_photo.assert_awaited_once()
    adapter._bot.set_my_profile_photo.assert_awaited_once()


class _FakeInputProfilePhotoStatic:
    def __init__(self, photo):
        self.photo = photo


@pytest.mark.asyncio
async def test_avatar_uses_input_profile_photo_static(tmp_path, monkeypatch):
    import telegram

    monkeypatch.setattr(telegram, "InputProfilePhotoStatic", _FakeInputProfilePhotoStatic, raising=False)
    avatar = tmp_path / "a.jpg"
    avatar.write_bytes(b"\xff\xd8\xff fake")
    bot = AsyncMock()

    assert await branding.sync_avatar(bot, avatar) is True

    photo = bot.set_my_profile_photo.await_args.kwargs["photo"]
    assert isinstance(photo, _FakeInputProfilePhotoStatic)
    assert photo.photo.name == str(avatar)


@pytest.mark.asyncio
async def test_avatar_without_input_profile_photo_passes_file(tmp_path, monkeypatch):
    import telegram

    monkeypatch.setattr(telegram, "InputProfilePhotoStatic", None, raising=False)
    avatar = tmp_path / "a.jpg"
    avatar.write_bytes(b"x")
    bot = AsyncMock()

    assert await branding.sync_avatar(bot, avatar) is True
    assert bot.set_my_profile_photo.await_args.kwargs["photo"].name == str(avatar)


@pytest.mark.asyncio
async def test_avatar_falls_back_to_raw_remove_api(tmp_path):
    avatar = tmp_path / "a.jpg"
    avatar.write_bytes(b"x")
    bot = AsyncMock()
    bot.remove_my_profile_photo.side_effect = RuntimeError("boom")

    assert await branding.sync_avatar(bot, avatar) is True
    bot.do_api_request.assert_awaited_once_with("removeMyProfilePhoto")
    bot.set_my_profile_photo.assert_awaited_once()


@pytest.mark.asyncio
async def test_avatar_skipped_on_old_ptb(tmp_path, monkeypatch):
    avatar = tmp_path / "a.jpg"
    avatar.write_bytes(b"x")
    warning = Mock()
    monkeypatch.setattr(branding.logger, "warning", warning)
    bot = SimpleNamespace(remove_my_profile_photo=AsyncMock())

    assert await branding.sync_avatar(bot, avatar) is False
    assert "22.7" in warning.call_args.args[0]
    bot.remove_my_profile_photo.assert_not_awaited()


@pytest.mark.asyncio
async def test_avatar_skipped_when_asset_missing(tmp_path):
    bot = AsyncMock()
    assert await branding.sync_avatar(bot, tmp_path / "missing.jpg") is False
    bot.set_my_profile_photo.assert_not_awaited()


@pytest.mark.asyncio
async def test_avatar_upload_failure_does_not_raise(tmp_path):
    avatar = tmp_path / "a.jpg"
    avatar.write_bytes(b"x")
    bot = AsyncMock()
    bot.set_my_profile_photo.side_effect = RuntimeError("telegram down")
    assert await branding.sync_avatar(bot, avatar) is False


# ── assets + real plugin discovery ────────────────────────────────────


def test_branding_assets_are_jpeg():
    for asset in (branding.AVATAR_PATH, branding.WELCOME_IMAGE_PATH):
        assert asset.exists(), asset
        assert asset.read_bytes()[:3] == b"\xff\xd8\xff"
    result = subprocess.run(["file", str(branding.AVATAR_PATH)], capture_output=True, text=True, check=True)
    assert "JPEG image data" in result.stdout


@pytest.mark.asyncio
async def test_enabled_plugin_handles_start_through_invoke_hook(tmp_path, monkeypatch):
    """plugins.enabled: [janitor] → entry point loads → hook answers /start."""
    from hermes_cli import plugins
    from hermes_cli.lifecycle import invoke_hook
    from hermes_constants import get_hermes_home

    home = get_hermes_home()
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.yaml").write_text(yaml.safe_dump({"plugins": {"enabled": ["janitor"]}}), encoding="utf-8")
    monkeypatch.setattr(branding, "WELCOME_IMAGE_PATH", tmp_path / "missing.jpg")
    monkeypatch.setattr(branding, "AVATAR_PATH", tmp_path / "missing.jpg")
    plugins._reset_plugin_managers_for_tests()
    try:
        plugins.discover_plugins(force=True)
        adapter = _adapter()
        results = invoke_hook(
            "pre_gateway_dispatch",
            event=_event("/start"),
            gateway=SimpleNamespace(adapters={Platform.TELEGRAM: adapter}),
            session_store=None,
        )
        await _drain()
    finally:
        plugins._reset_plugin_managers_for_tests()

    assert {"action": "skip", "reason": "janitor-telegram-welcome"} in results
    adapter._bot.send_message.assert_awaited()


def test_plugin_not_loaded_unless_enabled():
    from hermes_cli import plugins
    from hermes_constants import get_hermes_home

    home = get_hermes_home()
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.yaml").write_text(yaml.safe_dump({"plugins": {"enabled": []}}), encoding="utf-8")
    plugins._reset_plugin_managers_for_tests()
    try:
        plugins.discover_plugins(force=True)
        results = plugins.invoke_hook("pre_gateway_dispatch", event=_event("/start"), gateway=None)
    finally:
        plugins._reset_plugin_managers_for_tests()
    assert results == []
