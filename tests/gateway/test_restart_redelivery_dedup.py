"""Tests for /restart idempotency guard against Telegram update re-delivery.

When PTB's graceful-shutdown ACK call (the final `get_updates` on exit) fails
with a network error, Telegram re-delivers the `/restart` message to the new
gateway process.  Without a dedup guard, the new gateway would process
`/restart` again and immediately restart — a self-perpetuating loop.
"""
import json
import time
from unittest.mock import MagicMock

import pytest

import gateway.run as gateway_run
from gateway.platforms.event import MessageEvent, MessageType
from tests.gateway.restart_test_helpers import make_restart_runner, make_restart_source


def _make_restart_event(update_id: int | None = 100) -> MessageEvent:
    return MessageEvent(
        text="/restart",
        message_type=MessageType.TEXT,
        source=make_restart_source(),
        message_id="m1",
        platform_update_id=update_id,
    )


@pytest.mark.asyncio
async def test_redelivered_restart_with_older_update_id_is_ignored(tmp_path, monkeypatch):
    """update_id strictly LESS than the recorded one is also a redelivery."""
    monkeypatch.setattr(gateway_run, "_hermes_home", tmp_path)
    monkeypatch.delenv("INVOCATION_ID", raising=False)

    marker = tmp_path / ".restart_last_processed.json"
    marker.write_text(json.dumps({
        "platform": "telegram",
        "update_id": 12345,
        "requested_at": time.time() - 5,
    }))

    runner, _adapter = make_restart_runner()
    runner.request_restart = MagicMock()

    event = _make_restart_event(update_id=12344)  # older update — shouldn't happen,
                                                  # but if Telegram does re-deliver
                                                  # something older, treat as stale
    result = await runner._handle_restart_command(event)

    assert result == ""
    runner.request_restart.assert_not_called()


@pytest.mark.asyncio
async def test_stale_marker_older_than_5min_does_not_block(tmp_path, monkeypatch):
    """A marker older than the 5-minute window is ignored — fresh /restart proceeds."""
    monkeypatch.setattr(gateway_run, "_hermes_home", tmp_path)
    monkeypatch.delenv("INVOCATION_ID", raising=False)

    marker = tmp_path / ".restart_last_processed.json"
    marker.write_text(json.dumps({
        "platform": "telegram",
        "update_id": 12345,
        "requested_at": time.time() - 600,  # 10 minutes ago
    }))

    runner, _adapter = make_restart_runner()
    runner.request_restart = MagicMock(return_value=True)

    # Same update_id as the stale marker, but the marker is too old to trust
    event = _make_restart_event(update_id=12345)
    await runner._handle_restart_command(event)

    runner.request_restart.assert_called_once()


@pytest.mark.asyncio
async def test_event_without_update_id_bypasses_dedup(tmp_path, monkeypatch):
    """Events with no platform_update_id (non-Telegram, CLI fallback) aren't gated."""
    monkeypatch.setattr(gateway_run, "_hermes_home", tmp_path)
    monkeypatch.delenv("INVOCATION_ID", raising=False)

    marker = tmp_path / ".restart_last_processed.json"
    marker.write_text(json.dumps({
        "platform": "telegram",
        "update_id": 999999,
        "requested_at": time.time(),
    }))

    runner, _adapter = make_restart_runner()
    runner.request_restart = MagicMock(return_value=True)

    # No update_id — the dedup check should NOT kick in
    event = _make_restart_event(update_id=None)
    await runner._handle_restart_command(event)

    runner.request_restart.assert_called_once()


@pytest.mark.asyncio
async def test_different_platform_bypasses_dedup(tmp_path, monkeypatch):
    """Marker from Telegram doesn't block a /restart from another platform."""
    from gateway.config import Platform
    from gateway.session import SessionSource

    monkeypatch.setattr(gateway_run, "_hermes_home", tmp_path)
    monkeypatch.delenv("INVOCATION_ID", raising=False)

    marker = tmp_path / ".restart_last_processed.json"
    marker.write_text(json.dumps({
        "platform": "telegram",
        "update_id": 12345,
        "requested_at": time.time(),
    }))

    runner, _adapter = make_restart_runner()
    runner.request_restart = MagicMock(return_value=True)

    # /restart from Discord — not a redelivery candidate
    discord_source = SessionSource(
        platform=Platform.DISCORD,
        chat_id="discord-chan",
        chat_type="dm",
        user_id="u1",
    )
    event = MessageEvent(
        text="/restart",
        message_type=MessageType.TEXT,
        source=discord_source,
        message_id="m1",
        platform_update_id=12345,
    )
    await runner._handle_restart_command(event)

    runner.request_restart.assert_called_once()


@pytest.mark.asyncio
async def test_marker_missing_but_booted_from_restart_ignores_redelivery(tmp_path, monkeypatch):
    """Missing marker + just booted from a /restart + young process → treat as stale.

    Reproduces the infinite-loop scenario (issue #18528): the dedup marker went
    missing, so the update_id comparison can't run. Because this process booted
    from a chat-originated /restart and is still within the post-boot window,
    the redelivered /restart is suppressed instead of re-restarting the gateway.
    """
    monkeypatch.setattr(gateway_run, "_hermes_home", tmp_path)
    monkeypatch.delenv("INVOCATION_ID", raising=False)

    runner, _adapter = make_restart_runner()
    runner.request_restart = MagicMock(return_value=True)
    runner._booted_from_restart = True
    runner._startup_time = time.time()

    event = _make_restart_event(update_id=100)
    result = await runner._handle_restart_command(event)

    assert result == ""  # silently ignored
    runner.request_restart.assert_not_called()
    # One-shot: the flag is consumed so a later legitimate /restart is honored.
    assert runner._booted_from_restart is False




@pytest.mark.asyncio
@pytest.mark.parametrize("platform_name", ["slack", "discord"])
@pytest.mark.parametrize("changed", [None, "message_id", "chat_id", "scope_id", "profile", "user_id", "thread_id"])
async def test_restart_identity_survives_new_process_without_crossing_conversations(
    tmp_path, monkeypatch, platform_name, changed,
):
    """#121325: exact replay is ignored, while new messages and other scopes still work."""
    import dataclasses
    from gateway.config import Platform
    from gateway.session import SessionSource

    monkeypatch.setattr(gateway_run, "_hermes_home", tmp_path)
    source = SessionSource(
        platform=Platform(platform_name), chat_id="room", user_id="owner",
        scope_id="workspace", profile="personal", thread_id="thread",
    )
    event = MessageEvent(text="/restart", source=source, message_type=MessageType.TEXT, message_id="msg")
    old, _ = make_restart_runner()
    old.request_restart = MagicMock(return_value=True)
    await old._handle_restart_command(event)
    old.request_restart.assert_called_once()

    fresh, _ = make_restart_runner()
    fresh.request_restart = MagicMock(return_value=True)
    fresh._booted_from_restart = True
    if changed == "message_id":
        event = dataclasses.replace(event, message_id="other")
    elif changed:
        event = dataclasses.replace(event, source=dataclasses.replace(source, **{changed: "other"}))
    await fresh._handle_restart_command(event)
    assert fresh.request_restart.call_count == (0 if changed is None else 1)


@pytest.mark.parametrize("marker", [None, {}, [], {"message_identity": {}}, "broken"])
def test_unidentified_restart_marker_cannot_suppress_fresh_commands(tmp_path, marker):
    from gateway.config import Platform
    from gateway.session import SessionSource
    from gateway.restart_dedup import is_recorded_restart

    path = tmp_path / "marker.json"
    if marker is not None:
        path.write_text(marker if isinstance(marker, str) else json.dumps(marker))
    event = MessageEvent(text="/restart", source=SessionSource(platform=Platform.SLACK, chat_id="room"),
                         message_type=MessageType.TEXT, message_id="msg")
    assert not is_recorded_restart(event, path, now=time.time(), booted_from_restart=True)
