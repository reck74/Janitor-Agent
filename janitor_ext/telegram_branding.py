"""Janitor Telegram identity, isolated from the upstream transport adapter."""

import asyncio
from io import BytesIO
import logging
from pathlib import Path

try:
    from telegram.error import TelegramError
except ImportError:
    class TelegramError(Exception):
        """Unavailable transport; importing the adapter remains optional."""

try:
    from telegram import InputProfilePhotoStatic
except ImportError:
    InputProfilePhotoStatic = None

logger = logging.getLogger(__name__)

_JANITOR_ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets" / "janitor"
_JANITOR_TELEGRAM_AVATAR_PATH = _JANITOR_ASSETS_DIR / "janitor_avatar_telegram.jpg"
_JANITOR_WELCOME_PATH = _JANITOR_ASSETS_DIR / "telegram_welcome.jpg"
_JANITOR_WELCOME_TEXT = (
    "DENEGADO. No hay tiempo para presentaciones. "
    "Soy The Janitor. Trae tu código roto, tu arquitectura frágil "
    "y tus secretos hardcodeados. Los limpio. Los audito. "
    "Los hago a prueba de balas. Escribe /topic para separar tus conversaciones "
    "en tópicos y mantener el contexto organizado. Comienza."
)

def _safe_error(error: Exception) -> str:
    # Reuse the transport's fail-closed redactor after its module is initialized.
    from plugins.platforms.telegram.adapter import _redact_telegram_error_text
    return _redact_telegram_error_text(error)


class JanitorTelegramBrandingMixin:
    """Branding uses the adapter's existing authorization and routing contracts."""

    async def _set_janitor_avatar(self) -> None:
        """Forcibly set the bot profile photo to the Janitor avatar on every connect."""
        if not _JANITOR_TELEGRAM_AVATAR_PATH.exists():
            logger.warning(
                "[%s] Janitor avatar asset not found at %s; skipping Telegram avatar setup",
                self.name,
                _JANITOR_TELEGRAM_AVATAR_PATH,
            )
            return

        if not hasattr(self._bot, "set_my_profile_photo"):
            logger.warning(
                "[%s] Janitor Telegram avatar requires python-telegram-bot >= 22.7. "
                "Installed version lacks set_my_profile_photo. "
                "Run: pip install 'python-telegram-bot[webhooks]>=22.7,<23'",
                self.name,
            )
            return

        try:
            remove_media_ok = await self._bot.remove_my_profile_photo()
            logger.debug(
                "[%s] removeMyProfilePhoto result: %s",
                self.name, remove_media_ok,
            )
        except (TelegramError, OSError, AttributeError, RuntimeError, TypeError, ValueError) as exc:
            logger.debug(
                "[%s] removeMyProfilePhoto not available or failed: %s",
                self.name, _safe_error(exc),
            )
            try:
                await self._bot.do_api_request("removeMyProfilePhoto")
                logger.debug("[%s] removeMyProfilePhoto (raw) succeeded", self.name)
            except (TelegramError, AttributeError, RuntimeError) as raw_exc:
                logger.debug(
                    "[%s] removeMyProfilePhoto (raw) also failed: %s",
                    self.name, _safe_error(raw_exc),
                )

        try:
            with BytesIO(await asyncio.to_thread(_JANITOR_TELEGRAM_AVATAR_PATH.read_bytes)) as photo_file:
                photo_file.name = str(_JANITOR_TELEGRAM_AVATAR_PATH)
                if InputProfilePhotoStatic is not None:
                    profile_photo = InputProfilePhotoStatic(photo=photo_file)
                    await self._bot.set_my_profile_photo(photo=profile_photo)
                else:
                    await self._bot.set_my_profile_photo(photo=photo_file)
            logger.info("[%s] Janitor Telegram avatar applied successfully", self.name)
        except (TelegramError, OSError, AttributeError, RuntimeError, TypeError, ValueError) as exc:
            logger.warning(
                "[%s] Failed to set Janitor Telegram avatar: %s",
                self.name,
                _safe_error(exc),
            )

    async def _handle_start(self, update, context) -> None:
        """Welcome only admitted senders, retaining the incoming Telegram topic."""
        msg = self._effective_update_message(update)
        if not msg or not getattr(msg, "text", None):
            return
        if not self._should_process_message(msg, is_command=True):
            return
        if not self._is_user_authorized_from_message(msg):
            self._log_blocked_user(msg)
            return
        # Intake may admit an unauthorized DM specifically so the runner can
        # pair or decline it. Only its full authorization callback can approve
        # this local welcome; unknown/denied senders keep the upstream command
        # route instead of having /start consume their pairing request.
        source = self._source_from_message_for_auth(msg)
        if self._is_sender_authorized(
            source.user_id, chat_type=source.chat_type, chat_id=source.chat_id,
            is_bot=source.is_bot, thread_id=source.thread_id,
        ) is not True:
            await self._handle_command(update, context)
            return
        chat_id = getattr(getattr(msg, "chat", None), "id", None)
        if chat_id is None:
            return
        await self._ensure_forum_commands(msg)
        metadata = {}
        direct_topic = getattr(msg, "direct_messages_topic", None)
        if direct_topic is not None:
            metadata["direct_messages_topic_id"] = direct_topic.topic_id
        routing = self._thread_kwargs_for_send(
            str(chat_id), self._effective_message_thread_id(msg), metadata)
        routing = {key: value for key, value in routing.items() if value is not None}
        if _JANITOR_WELCOME_PATH.exists():
            try:
                with BytesIO(await asyncio.to_thread(_JANITOR_WELCOME_PATH.read_bytes)) as photo_file:
                    await self._bot.send_photo(
                        chat_id=chat_id, photo=photo_file, caption=_JANITOR_WELCOME_TEXT, **routing)
                return
            except (TelegramError, OSError, AttributeError, RuntimeError, TypeError, ValueError) as exc:
                logger.warning("[%s] Failed to send Janitor Telegram welcome image: %s",
                               self.name, _safe_error(exc))
        try:
            await self._bot.send_message(chat_id=chat_id, text=_JANITOR_WELCOME_TEXT, **routing)
        except (TelegramError, OSError, AttributeError, RuntimeError, TypeError, ValueError) as exc:
            logger.warning("[%s] Failed to send Janitor Telegram welcome text: %s",
                           self.name, _safe_error(exc))
