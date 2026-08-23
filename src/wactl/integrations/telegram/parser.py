"""Parse a Telegram Update envelope into a uniform internal shape.

The webhook handler iterates over :func:`parse_envelope`'s output and hands
each parsed message to the dispatcher. The shape is intentionally close to
the old WhatsApp one — ``ParsedMessage(user, message)`` — so that the
dispatcher and command base stay platform-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from wactl.exceptions import WebhookError
from wactl.models.telegram import Message as TelegramMessage
from wactl.models.telegram import Update
from wactl.models.user import UserContext

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ParsedMessage:
    """The webhook handler's per-message view, used by the dispatcher.

    Attributes
    ----------
    user:
        The :class:`UserContext` carrying ``chat_id``, ``message_id``, etc.
    body:
        Text body (slash-command) if the message is text, else ``None``.
    media_id:
        Inbound ``file_id`` if the message carries media, else ``None``.
    media_mime:
        MIME type of the inbound media if known, else ``None``.
    media_filename:
        Filename of the inbound document if any, else ``None``.
    """

    user: UserContext
    body: str | None
    media_id: str | None
    media_mime: str | None
    media_filename: str | None

    @property
    def is_text(self) -> bool:
        return self.body is not None

    @property
    def has_media(self) -> bool:
        return self.media_id is not None


def parse_envelope(raw_body: dict[str, Any]) -> list[ParsedMessage]:
    """Parse a Telegram Update envelope into a list of :class:`ParsedMessage`.

    Telegram sends one Update per webhook POST (no batched array like Meta).
    We return a list for symmetry with the WhatsApp parser and so callers
    can iterate uniformly.

    Raises :class:`WebhookError` on malformed JSON / missing required fields.
    """
    try:
        update = Update.model_validate(raw_body)
    except Exception as exc:
        raise WebhookError(f"Malformed Telegram Update envelope: {exc}") from exc

    # wactl only handles fresh ``message`` events today.
    message = update.message or update.edited_message
    if message is None:
        logger.debug("telegram.update_ignored", update_id=update.update_id)
        return []

    parsed = _parse_message(message)
    return [parsed] if parsed is not None else []


def _parse_message(message: TelegramMessage) -> ParsedMessage | None:
    """Extract user + body/media from a single Message. Returns None if not actionable."""
    user = _user_from_message(message)
    if user is None:
        logger.warning("telegram.message_skipped_no_user", message_id=message.message_id)
        return None

    body = message.text or message.caption
    media_id, media_mime, media_filename = _extract_media(message)

    return ParsedMessage(
        user=user,
        body=body,
        media_id=media_id,
        media_mime=media_mime,
        media_filename=media_filename,
    )


def _user_from_message(message: TelegramMessage) -> UserContext | None:
    """Build a UserContext from a Telegram Message."""
    if message.from_ is None:
        # Channel posts and some group events have no `from`; skip for now.
        return None
    return UserContext(
        chat_id=message.chat.id,
        username=message.from_.username,
        first_name=message.from_.first_name,
        message_id=message.message_id,
    )


def _extract_media(message: TelegramMessage) -> tuple[str | None, str | None, str | None]:
    """Return ``(file_id, mime, filename)`` for the first media attachment.

    Priority: photo (highest resolution) > document > voice > audio > video.
    Photo is a list of PhotoSize; we pick the LAST (highest resolution)
    per https://core.telegram.org/bots/api#photosize.
    """
    if message.photo:
        biggest = message.photo[-1]
        # Telegram photos are JPEG by default; the API doesn't return a mime.
        return biggest.file_id, "image/jpeg", None

    if message.document is not None:
        return (
            message.document.file_id,
            message.document.mime_type,
            message.document.file_name,
        )

    if message.voice is not None:
        return message.voice.file_id, message.voice.mime_type or "audio/ogg", None

    if message.audio is not None:
        return message.audio.file_id, message.audio.mime_type, message.audio.file_name

    if message.video is not None:
        return message.video.file_id, message.video.mime_type, message.video.file_name

    return None, None, None


__all__ = ["ParsedMessage", "parse_envelope"]
