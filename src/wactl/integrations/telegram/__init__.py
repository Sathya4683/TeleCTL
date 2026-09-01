"""Telegram Bot API integration.

Public surface used by commands and the webhook handler:

- :class:`TelegramClient` — HTTP client for the Bot API.
- :func:`parse_envelope` — webhook payload → list of :class:`ParsedMessage`.
- :func:`download` — resolve a ``file_id`` and download its bytes.
- :func:`send_text`, :func:`send_photo`, :func:`send_document`,
  :func:`send_audio`, :func:`send_voice`, :func:`send_typing`
  — high-level outbound helpers.
"""

from wactl.integrations.telegram.client import TelegramApiError, TelegramClient
from wactl.integrations.telegram.media import download
from wactl.integrations.telegram.messages import (
    send_audio,
    send_document,
    send_photo,
    send_text,
    send_typing,
    send_voice,
)
from wactl.integrations.telegram.parser import ParsedMessage, parse_envelope

__all__ = [
    "ParsedMessage",
    "TelegramApiError",
    "TelegramClient",
    "download",
    "parse_envelope",
    "send_audio",
    "send_document",
    "send_photo",
    "send_text",
    "send_typing",
    "send_voice",
]
