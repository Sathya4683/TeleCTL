"""Parse a raw Meta webhook payload into typed internal models.

This module is the only place in the codebase that knows the Meta envelope
shape. Everything downstream operates on :class:`ParsedMessage` /
:class:`ParsedMediaMessage` / :class:`UserContext`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from wactl.exceptions import WebhookError
from wactl.models.user import UserContext
from wactl.models.webhook import (
    MediaMessage,
    TextMessage,
    WhatsAppEnvelope,
)


@dataclass(frozen=True)
class ParsedTextMessage:
    """A text message + the user who sent it."""

    user: UserContext
    message: TextMessage

    @property
    def body(self) -> str:
        return self.message.body


@dataclass(frozen=True)
class ParsedMediaMessage:
    """A media-bearing message + the user who sent it."""

    user: UserContext
    message: MediaMessage

    @property
    def media_id(self) -> str | None:
        return self.message.media_id

    @property
    def mime_type(self) -> str | None:
        return self.message.media_mime


ParsedMessage = ParsedTextMessage | ParsedMediaMessage


def _build_user(
    envelope: WhatsAppEnvelope,
    message: TextMessage | MediaMessage,
) -> UserContext:
    contact = envelope.primary_contact()
    return UserContext(
        phone=message.from_,
        name=contact.profile.name if contact else None,
        message_id=message.id,
        waba_id=envelope.entry[0].id,
        phone_number_id=envelope.primary_metadata().phone_number_id,
    )


def parse_envelope(raw: dict[str, Any] | WhatsAppEnvelope) -> list[ParsedMessage]:
    """Parse a webhook payload into a list of parsed messages.

    Returns an empty list if the payload contains only statuses/errors
    (not user messages). Raises :class:`WebhookError` on malformed input.
    """
    if isinstance(raw, dict):
        try:
            envelope = WhatsAppEnvelope.model_validate(raw)
        except Exception as exc:  # wrap any pydantic ValidationError
            raise WebhookError(
                f"Failed to parse webhook envelope: {exc}",
                user_message="",
            ) from exc
    else:
        envelope = raw

    out: list[ParsedMessage] = []
    for message in envelope.all_messages():
        user = _build_user(envelope, message)
        if isinstance(message, TextMessage):
            out.append(ParsedTextMessage(user=user, message=message))
        elif isinstance(message, MediaMessage):
            out.append(ParsedMediaMessage(user=user, message=message))
        else:  # pragma: no cover — defensive
            raise WebhookError(f"Unknown message type: {type(message).__name__}")
    return out


def first_text(payloads: list[ParsedMessage]) -> ParsedTextMessage | None:
    """Return the first text message in a list, ignoring media."""
    for p in payloads:
        if isinstance(p, ParsedTextMessage):
            return p
    return None


def first_media(payloads: list[ParsedMessage]) -> ParsedMediaMessage | None:
    """Return the first media message in a list, ignoring text."""
    for p in payloads:
        if isinstance(p, ParsedMediaMessage):
            return p
    return None


__all__ = [
    "ParsedMediaMessage",
    "ParsedMessage",
    "ParsedTextMessage",
    "first_media",
    "first_text",
    "parse_envelope",
]
