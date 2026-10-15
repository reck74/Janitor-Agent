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
from janitor_ext import telegram_branding as branding_module
from plugins.platforms.telegram import adapter as telegram_module
from plugins.platforms.telegram.adapter import TelegramAdapter


def _make_adapter() -> TelegramAdapter:
    adapter = TelegramAdapter(PlatformConfig(enabled=True, token="***", extra={}))
    adapter._bot = AsyncMock()
    adapter._bot.id = 999
    adapter._bot.username = "janitor_bot"
    # Production adapters receive the runner's full authorization callback.
    adapter.set_authorization_check(lambda *args, **kwargs: True)
    return adapter


@pytest.mark.asyncio
async def test_set_janitor_avatar_on_connect(tmp_path, monkeypatch):
    """connect() should apply Janitor branding after a successful startup."""
    avatar_path = tmp_path / "janitor_avatar_telegram.jpg"
    avatar_path.write_bytes(b"fake-jpg")
    monkeypatch.setattr(branding_module, "_JANITOR_TELEGRAM_AVATAR_PATH", avatar_path, raising=False)

    remove_my_profile_photo = AsyncMock(return_value=True)
    set_my_profile_photo = AsyncMock(return_value=SimpleNamespace(id="photo"))
    delete_webhook = AsyncMock(return_value=None)
    set_my_commands = AsyncMock(return_value=None)
    bot = SimpleNamespace(
        remove_my_profile_photo=remove_my_profile_photo,
        set_my_profile_photo=set_my_profile_photo,
        delete_webhook=delete_webhook,
        set_my_commands=set_my_commands,
    )
    app = SimpleNamespace(
        bot=bot,
        add_handler=Mock(),
        initialize=AsyncMock(return_value=None),
        start=AsyncMock(return_value=None),
        updater=SimpleNamespace(
            start_polling=AsyncMock(return_value=None),
            start_webhook=AsyncMock(return_value=None),
        ),
    )

    class FakeBuilder:
        def application_class(self, _cls, _kwargs):
            return self

        def token(self, _token):
            return self

        def base_url(self, _url):
            return self

        def base_file_url(self, _url):
            return self

        def local_mode(self, _enabled):
            return self

        def request(self, _request):
            return self

        def get_updates_request(self, _request):
            return self

        def concurrent_updates(self, _processor):
            return self

        def build(self):
            return app

    # Heap type: required so _instrument_polling_request's __class__ swap is legal.
    class FakeRequest:
        pass

    adapter = _make_adapter()
    adapter._fallback_ips = Mock(return_value=[])
    adapter._acquire_platform_lock = Mock(return_value=True)
    adapter._mark_connected = Mock()
    adapter._setup_dm_topics = AsyncMock(return_value=None)
    # Branding is applied before polling; stub the 60s progress gate (#67498).
    adapter._start_polling_resilient = AsyncMock(return_value=True)

    # Replace the module-global Application, not the PTB class attribute —
    # PTB 22.8's Application is an immutable (non-heap) type.
    monkeypatch.setattr(
        telegram_module,
        "Application",
        SimpleNamespace(builder=Mock(return_value=FakeBuilder())),
    )
    monkeypatch.setattr(
        telegram_module,
        "HTTPXRequest",
        Mock(side_effect=lambda *a, **k: FakeRequest()),
    )
    monkeypatch.setattr(telegram_module, "discover_fallback_ips", AsyncMock(return_value=[]))
    monkeypatch.setattr(telegram_module, "resolve_proxy_url", Mock(return_value=None))

    avatar_spy = AsyncMock(wraps=adapter._set_janitor_avatar)
    adapter._set_janitor_avatar = avatar_spy

    assert await adapter.connect() is True

    avatar_spy.assert_awaited_once()
    remove_my_profile_photo.assert_awaited_once()
    set_my_profile_photo.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_janitor_avatar_idempotent(tmp_path, monkeypatch):
    """Calling the avatar setter twice should remain safe."""
    avatar_path = tmp_path / "janitor_avatar_telegram.jpg"
    avatar_path.write_bytes(b"fake-jpg")
    monkeypatch.setattr(branding_module, "_JANITOR_TELEGRAM_AVATAR_PATH", avatar_path, raising=False)

    adapter = _make_adapter()
    adapter._bot.remove_my_profile_photo = AsyncMock(return_value=True)
    adapter._bot.set_my_profile_photo = AsyncMock(return_value=SimpleNamespace(id="photo"))

    await adapter._set_janitor_avatar()
    await adapter._set_janitor_avatar()

    assert adapter._bot.set_my_profile_photo.await_count == 2
    assert adapter._bot.remove_my_profile_photo.await_count == 2


@pytest.mark.asyncio
async def test_set_janitor_avatar_skips_incomplete_bot(tmp_path, monkeypatch):
    """Old PTB without set_my_profile_photo should warn and skip avatar setup."""
    avatar_path = tmp_path / "janitor_avatar_telegram.jpg"
    avatar_path.write_bytes(b"fake-jpg")
    monkeypatch.setattr(branding_module, "_JANITOR_TELEGRAM_AVATAR_PATH", avatar_path, raising=False)
    warning = Mock()
    monkeypatch.setattr(branding_module.logger, "warning", warning)

    remove_my_profile_photo = AsyncMock(return_value=True)
    do_api_request = AsyncMock(return_value=True)
    bot = SimpleNamespace(remove_my_profile_photo=remove_my_profile_photo, do_api_request=do_api_request)

    adapter = _make_adapter()
    adapter._bot = bot

    await adapter._set_janitor_avatar()

    assert not hasattr(bot, "set_my_profile_photo")
    assert warning.called
    assert "set_my_profile_photo" in warning.call_args.args[0]
    assert "22.7" in warning.call_args.args[0]
    remove_my_profile_photo.assert_not_awaited()
    do_api_request.assert_not_awaited()


@pytest.mark.asyncio
async def test_remove_my_profile_photo_fallback_on_raw_api_failure(tmp_path, monkeypatch):
    """If remove_my_profile_photo fails, the raw API fallback should run."""
    avatar_path = tmp_path / "janitor_avatar_telegram.jpg"
    avatar_path.write_bytes(b"fake-jpg")
    monkeypatch.setattr(branding_module, "_JANITOR_TELEGRAM_AVATAR_PATH", avatar_path, raising=False)

    adapter = _make_adapter()
    adapter._bot.remove_my_profile_photo.side_effect = RuntimeError("boom")
    adapter._bot.do_api_request = AsyncMock(return_value=True)

    await adapter._set_janitor_avatar()

    adapter._bot.do_api_request.assert_awaited_once_with("removeMyProfilePhoto")
    adapter._bot.set_my_profile_photo.assert_awaited_once()


# ── _set_janitor_avatar  ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_set_janitor_avatar_always_uploads(tmp_path, monkeypatch):
    """Avatar must upload on every connect — no flag file gate."""
    avatar_path = tmp_path / "janitor_avatar_telegram.jpg"
    avatar_path.write_bytes(b"fake-jpg")
    monkeypatch.setattr(branding_module, "_JANITOR_TELEGRAM_AVATAR_PATH", avatar_path, raising=False)

    adapter = _make_adapter()

    await adapter._set_janitor_avatar()

    adapter._bot.remove_my_profile_photo.assert_awaited_once()
    adapter._bot.set_my_profile_photo.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_janitor_avatar_skips_when_asset_missing(tmp_path, monkeypatch):
    """Missing avatar asset must not block startup."""
    missing = tmp_path / "nonexistent.jpg"
    monkeypatch.setattr(branding_module, "_JANITOR_TELEGRAM_AVATAR_PATH", missing, raising=False)

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

    monkeypatch.setattr(branding_module, "_JANITOR_TELEGRAM_AVATAR_PATH", avatar_path, raising=False)
    monkeypatch.setattr(branding_module, "InputProfilePhotoStatic", FakeInputProfilePhotoStatic, raising=False)

    adapter = _make_adapter()

    await adapter._set_janitor_avatar()

    assert hasattr(captured["photo"], "read")
    assert getattr(captured["photo"], "name", None) == str(avatar_path)
    adapter._bot.set_my_profile_photo.assert_awaited_once()
    _, kwargs = adapter._bot.set_my_profile_photo.await_args
    assert kwargs["photo"] is not None
    assert "profile_photo" not in kwargs


@pytest.mark.asyncio
async def test_set_janitor_avatar_fallback_uses_photo_kwarg(tmp_path, monkeypatch):
    """Fallback upload path must still use photo=, not profile_photo=."""
    avatar_path = tmp_path / "janitor_avatar_telegram.jpg"
    avatar_path.write_bytes(b"fake-jpg")
    monkeypatch.setattr(branding_module, "_JANITOR_TELEGRAM_AVATAR_PATH", avatar_path, raising=False)
    monkeypatch.setattr(branding_module, "InputProfilePhotoStatic", None, raising=False)

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
    monkeypatch.setattr(branding_module, "_JANITOR_TELEGRAM_AVATAR_PATH", avatar_path, raising=False)
    warning = Mock()
    monkeypatch.setattr(branding_module.logger, "warning", warning)

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
    monkeypatch.setattr(branding_module, "_JANITOR_WELCOME_PATH", welcome_path, raising=False)

    adapter = _make_adapter()
    update = _start_update()

    await adapter._handle_start(update, SimpleNamespace())

    adapter._bot.send_photo.assert_awaited_once()
    _, kwargs = adapter._bot.send_photo.await_args
    assert kwargs["chat_id"] == 12345
    assert kwargs["caption"] == branding_module._JANITOR_WELCOME_TEXT
    assert "/topic" in kwargs["caption"]
    adapter._bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_start_falls_back_to_text_when_welcome_photo_missing(tmp_path, monkeypatch):
    """When the welcome image is absent, /start falls back to text only."""
    missing_path = tmp_path / "missing.jpg"
    monkeypatch.setattr(branding_module, "_JANITOR_WELCOME_PATH", missing_path, raising=False)

    adapter = _make_adapter()
    update = _start_update()

    await adapter._handle_start(update, SimpleNamespace())

    adapter._bot.send_photo.assert_not_awaited()
    adapter._bot.send_message.assert_awaited_once_with(
        chat_id=12345,
        text=branding_module._JANITOR_WELCOME_TEXT,
    )


def test_telegram_avatar_asset_is_jpeg():
    asset = ROOT / "assets/janitor/janitor_avatar_telegram.jpg"

    assert asset.exists()
    assert asset.read_bytes()[:3] == b"\xff\xd8\xff"

    result = subprocess.run(["file", str(asset)], capture_output=True, text=True, check=True)
    assert "JPEG image data" in result.stdout


def _start_update(*, thread=None, forum=False, chat_type="private", user_id=7):
    chat = SimpleNamespace(id=12345, type=chat_type, is_forum=forum)
    message = SimpleNamespace(chat=chat, message_id=8, text="/start@janitor_bot",
                              from_user=SimpleNamespace(id=user_id, is_bot=False, username="tester"),
                              message_thread_id=thread, is_topic_message=forum or thread is not None,
                              entities=[], sender_chat=None, reply_to_message=None)
    return SimpleNamespace(effective_chat=chat, effective_message=message, message=message)


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked_by", ["user", "chat"])
async def test_start_preserves_upstream_intake_gates(monkeypatch, blocked_by):
    adapter = _make_adapter()
    adapter.config.extra.update({"require_mention": False})
    if blocked_by == "user":
        adapter.config.extra["allow_from"] = ["99999"]
        update = _start_update()
    else:
        adapter.config.extra["allowed_chats"] = ["99999"]
        update = _start_update(chat_type="supergroup", forum=True, thread=123)
    await adapter._handle_start(update, SimpleNamespace())
    adapter._bot.send_photo.assert_not_awaited()
    adapter._bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("photo", [True, False])
@pytest.mark.parametrize("thread,forum,chat_type,expected", [
    (123, True, "supergroup", 123),
    (None, True, "supergroup", None),
    (456, False, "private", 456),
])
async def test_start_preserves_topic_for_photo_and_fallback(tmp_path, monkeypatch, photo, thread, forum, chat_type, expected):
    welcome = tmp_path / "welcome.jpg"
    if photo:
        welcome.write_bytes(b"photo")
    monkeypatch.setattr(branding_module, "_JANITOR_WELCOME_PATH", welcome)
    adapter = _make_adapter()
    adapter.config.extra.update({"require_mention": False})
    await adapter._handle_start(_start_update(thread=thread, forum=forum, chat_type=chat_type), SimpleNamespace())
    sender = adapter._bot.send_photo if photo else adapter._bot.send_message
    sender.assert_awaited_once()
    assert sender.await_args.kwargs.get("message_thread_id") == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", [False, None])
@pytest.mark.parametrize("behavior", ["pair", "decline"])
async def test_start_defers_unapproved_dm_to_gateway_pairing_or_decline(decision, behavior):
    adapter = _make_adapter()
    adapter.config.extra.update({"allow_from": ["111"], "unauthorized_dm_behavior": behavior})
    adapter.set_authorization_check(lambda *args, **kwargs: decision)
    update = _start_update(user_id=7)
    event = SimpleNamespace(text="/start")
    adapter._build_triggered_event = AsyncMock(return_value=event)
    adapter.handle_message = AsyncMock()
    # This prefilter intentionally permits the DM so the gateway can answer it.
    assert adapter._is_user_authorized_from_message(update.message) is True
    await adapter._handle_start(update, SimpleNamespace())
    adapter.handle_message.assert_awaited_once_with(event)
    adapter._bot.send_photo.assert_not_awaited()
    adapter._bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_welcome_uses_full_context_authorization_callback():
    adapter = _make_adapter()
    authorize = Mock(return_value=True)
    adapter.set_authorization_check(authorize)
    await adapter._handle_start(_start_update(thread=456), SimpleNamespace())
    authorize.assert_called_with("7", "dm", "12345", thread_id="456")
    adapter._bot.send_photo.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["avatar", "welcome"])
async def test_branding_transport_failures_redact_credentials(operation, tmp_path, monkeypatch, caplog):
    asset = tmp_path / "photo.jpg"
    asset.write_bytes(b"photo")
    monkeypatch.setattr(branding_module, "_JANITOR_TELEGRAM_AVATAR_PATH", asset)
    monkeypatch.setattr(branding_module, "_JANITOR_WELCOME_PATH", asset)
    secret = "janitor-acceptance-secret-123456789"
    error = RuntimeError("Authorization: Bearer " + secret)
    adapter = _make_adapter()
    if operation == "avatar":
        adapter._bot.set_my_profile_photo.side_effect = error
        await adapter._set_janitor_avatar()
    else:
        adapter._bot.send_photo.side_effect = error
        adapter._bot.send_message.side_effect = error
        await adapter._handle_start(_start_update(), SimpleNamespace())
    assert "Failed to" in caplog.text
    assert secret not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [OSError, TypeError, ValueError])
async def test_avatar_raw_remove_failure_still_allows_upload(tmp_path, monkeypatch, failure):
    """A failed cosmetic API fallback must never escape into Telegram connect()."""
    asset = tmp_path / "avatar.jpg"
    asset.write_bytes(b"avatar-test")
    monkeypatch.setattr(branding_module, "_JANITOR_TELEGRAM_AVATAR_PATH", asset)
    adapter = _make_adapter()
    adapter._bot.remove_my_profile_photo = AsyncMock(side_effect=RuntimeError("unsupported"))
    adapter._bot.do_api_request = AsyncMock(side_effect=failure("cosmetic failure"))
    await adapter._set_janitor_avatar()
    adapter._bot.do_api_request.assert_awaited_once_with("removeMyProfilePhoto")
    adapter._bot.set_my_profile_photo.assert_awaited_once()
