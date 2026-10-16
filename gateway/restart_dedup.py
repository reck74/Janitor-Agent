"""Stable restart-command identity for adapters without ordered Telegram update IDs."""


def restart_message_identity(event):
    """Bind a message ID to its transport and conversation, never command text."""
    source = getattr(event, "source", None)
    platform = getattr(getattr(source, "platform", None), "value", None)
    message_id = getattr(event, "message_id", None) or getattr(source, "message_id", None)
    chat_id = getattr(source, "chat_id", None)
    if not platform or platform == "telegram" or not message_id or not chat_id:
        return None
    return {
        "platform": platform,
        "message_id": str(message_id),
        "chat_id": str(chat_id),
        "scope_id": str(getattr(source, "scope_id", None) or ""),
        "profile": str(getattr(source, "profile", None) or ""),
        "user_id": str(getattr(source, "user_id", None) or ""),
        "thread_id": str(getattr(source, "thread_id", None) or ""),
    }


def is_recorded_restart(event, marker_path, *, now, booted_from_restart):
    """Recognize the exact recorded message; malformed/old markers fail open."""
    import json

    identity = restart_message_identity(event)
    if identity is None:
        return False
    try:
        data = json.loads(marker_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict) or data.get("message_identity") != identity:
        return False
    requested_at = data.get("requested_at")
    return booted_from_restart or (
        isinstance(requested_at, (int, float)) and 0 <= now - requested_at <= 300
    )
