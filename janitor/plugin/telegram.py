"""Janitor Telegram branding: ``/start`` welcome and bot avatar.

Runs from the ``pre_gateway_dispatch`` hook so the upstream Telegram
adapter stays untouched. Upstream ignores ``/start``; Janitor answers it
with the welcome image, and syncs the bot avatar once per adapter the
first time that adapter delivers a message.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Optional

from janitor.home import ASSETS_ROOT

logger = logging.getLogger(__name__)

AVATAR_PATH = ASSETS_ROOT / "janitor_avatar_telegram.jpg"
WELCOME_IMAGE_PATH = ASSETS_ROOT / "telegram_welcome.jpg"
WELCOME_TEXT = (
    "DENEGADO. No hay tiempo para presentaciones. "
    "Soy The Janitor. Trae tu código roto, tu arquitectura frágil "
    "y tus secretos hardcodeados. Los limpio. Los audito. "
    "Los hago a prueba de balas. Escribe /topic para separar tus conversaciones "
    "en tópicos y mantener el contexto organizado. Comienza."
)

_avatar_synced: set[int] = set()
# Strong references so fire-and-forget tasks are not garbage-collected mid-run.
_background_tasks: set[asyncio.Task] = set()


def _platform_value(source: Any) -> str:
    platform = getattr(source, "platform", None)
    return str(getattr(platform, "value", platform) or "")


def is_start_command(text: Optional[str]) -> bool:
    """True for ``/start``, ``/start@BotName`` and ``/start <payload>``."""
    parts = (text or "").split(maxsplit=1)
    if not parts:
        return False
    return parts[0].split("@", 1)[0].lower() == "/start"


def resolve_adapter(gateway: Any, source: Any) -> Any:
    """Return the live adapter that delivered ``source`` (multiplex-aware)."""
    platform = getattr(source, "platform", None)
    profile = getattr(source, "profile", None)
    if profile:
        profile_map = (getattr(gateway, "_profile_adapters", None) or {}).get(profile) or {}
        adapter = profile_map.get(platform)
        if adapter is not None:
            return adapter
    return (getattr(gateway, "adapters", None) or {}).get(platform)


async def send_welcome(adapter: Any, chat_id: str, image_path: Optional[Path] = None) -> bool:
    """Send the welcome photo with caption, falling back to plain text."""
    image_path = image_path or WELCOME_IMAGE_PATH
    if image_path.exists():
        try:
            result = await adapter.send_image_file(
                chat_id=chat_id, image_path=str(image_path), caption=WELCOME_TEXT
            )
            if getattr(result, "success", True):
                return True
        except Exception as exc:
            logger.warning("Janitor welcome image failed, sending text: %s", exc)
    try:
        result = await adapter.send(chat_id=chat_id, content=WELCOME_TEXT)
        return bool(getattr(result, "success", True))
    except Exception as exc:
        logger.warning("Janitor welcome text failed: %s", exc)
        return False


async def sync_avatar(bot: Any, avatar_path: Optional[Path] = None) -> bool:
    """Replace the bot profile photo with the Janitor avatar.

    ``set_my_profile_photo`` exists from python-telegram-bot 22.7; older
    versions are skipped with a warning instead of failing the gateway.
    """
    avatar_path = avatar_path or AVATAR_PATH
    if bot is None or not avatar_path.exists():
        return False
    if not hasattr(bot, "set_my_profile_photo"):
        logger.warning(
            "Janitor Telegram avatar requires python-telegram-bot >= 22.7 "
            "(set_my_profile_photo missing); skipping"
        )
        return False

    try:
        await bot.remove_my_profile_photo()
    except Exception as exc:
        logger.debug("remove_my_profile_photo failed, trying raw API: %s", exc)
        try:
            await bot.do_api_request("removeMyProfilePhoto")
        except Exception as raw_exc:
            logger.debug("removeMyProfilePhoto (raw) failed: %s", raw_exc)

    try:
        try:
            from telegram import InputProfilePhotoStatic
        except ImportError:
            InputProfilePhotoStatic = None
        with open(avatar_path, "rb") as photo_file:
            if InputProfilePhotoStatic is not None:
                await bot.set_my_profile_photo(photo=InputProfilePhotoStatic(photo=photo_file))
            else:
                await bot.set_my_profile_photo(photo=photo_file)
        logger.info("Janitor Telegram avatar applied")
        return True
    except Exception as exc:
        logger.warning("Failed to set Janitor Telegram avatar: %s", exc)
        return False


def _spawn(coro) -> bool:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        coro.close()
        return False
    task = loop.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return True


def pre_gateway_dispatch(event: Any = None, gateway: Any = None, **_kwargs: Any):
    """``pre_gateway_dispatch`` hook: Telegram-only, otherwise a no-op."""
    source = getattr(event, "source", None)
    if source is None or _platform_value(source) != "telegram":
        return None
    adapter = resolve_adapter(gateway, source)
    if adapter is None:
        return None

    if id(adapter) not in _avatar_synced:
        _avatar_synced.add(id(adapter))
        _spawn(sync_avatar(getattr(adapter, "_bot", None)))

    if not is_start_command(getattr(event, "text", None)):
        return None
    chat_id = getattr(source, "chat_id", None)
    if not chat_id:
        return None
    if not _spawn(send_welcome(adapter, str(chat_id))):
        return None
    return {"action": "skip", "reason": "janitor-telegram-welcome"}
