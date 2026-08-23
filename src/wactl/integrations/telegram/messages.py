"""High-level outbound helpers used by commands.

Each helper returns the parsed :class:`TelegramResponse`. Commands that
need the new ``message_id`` for bookkeeping can read it off the result.
"""

from __future__ import annotations

from typing import Any

import structlog

from wactl.integrations.telegram.client import TelegramClient

logger = structlog.get_logger(__name__)


async def send_text(
    telegram: TelegramClient,
    *,
    chat_id: int,
    text: str,
    reply_to_message_id: int | None = None,
    parse_mode: str | None = None,
) -> str:
    """Send a plain (or Markdown/HTML) text message. Returns the new message_id."""
    resp = await telegram.send_message(
        chat_id,
        text,
        reply_to_message_id=reply_to_message_id,
        parse_mode=parse_mode,
    )
    new_id = _message_id(resp.result)
    logger.info("telegram.sent_text", chat_id=chat_id, message_id=new_id)
    return new_id


async def send_typing(telegram: TelegramClient, *, chat_id: int) -> None:
    """Show the typing indicator. Best-effort; ignore errors."""
    try:
        await telegram.send_chat_action(chat_id, "typing")
    except Exception as exc:  # pragma: no cover — typing is fire-and-forget
        logger.warning("telegram.typing_failed", error=str(exc))


async def send_photo(
    telegram: TelegramClient,
    *,
    chat_id: int,
    link: str | None = None,
    file_id: str | None = None,
    caption: str | None = None,
    reply_to_message_id: int | None = None,
) -> str:
    """Send a photo by URL or file_id. Exactly one of ``link`` / ``file_id`` required."""
    photo_arg = _require_media_arg(link=link, file_id=file_id, kind="photo")
    resp = await telegram.send_photo(
        chat_id, photo_arg, caption=caption, reply_to_message_id=reply_to_message_id
    )
    new_id = _message_id(resp.result)
    logger.info("telegram.sent_photo", chat_id=chat_id, message_id=new_id, bytes=len(link or file_id or ""))
    return new_id


async def send_document(
    telegram: TelegramClient,
    *,
    chat_id: int,
    link: str | None = None,
    file_id: str | None = None,
    caption: str | None = None,
    reply_to_message_id: int | None = None,
) -> str:
    """Send a generic file (PDF, DOCX, ZIP, ...) by URL or file_id."""
    doc_arg = _require_media_arg(link=link, file_id=file_id, kind="document")
    resp = await telegram.send_document(
        chat_id, doc_arg, caption=caption, reply_to_message_id=reply_to_message_id
    )
    new_id = _message_id(resp.result)
    logger.info("telegram.sent_document", chat_id=chat_id, message_id=new_id)
    return new_id


async def send_audio(
    telegram: TelegramClient,
    *,
    chat_id: int,
    link: str | None = None,
    file_id: str | None = None,
    caption: str | None = None,
    title: str | None = None,
    reply_to_message_id: int | None = None,
) -> str:
    """Send an audio file (MP3, M4A) by URL or file_id."""
    audio_arg = _require_media_arg(link=link, file_id=file_id, kind="audio")
    resp = await telegram.send_audio(
        chat_id,
        audio_arg,
        caption=caption,
        title=title,
        reply_to_message_id=reply_to_message_id,
    )
    new_id = _message_id(resp.result)
    logger.info("telegram.sent_audio", chat_id=chat_id, message_id=new_id)
    return new_id


async def send_voice(
    telegram: TelegramClient,
    *,
    chat_id: int,
    link: str | None = None,
    file_id: str | None = None,
    caption: str | None = None,
    reply_to_message_id: int | None = None,
) -> str:
    """Send a voice note (OGG/Opus) by URL or file_id."""
    voice_arg = _require_media_arg(link=link, file_id=file_id, kind="voice")
    resp = await telegram.send_voice(
        chat_id, voice_arg, caption=caption, reply_to_message_id=reply_to_message_id
    )
    new_id = _message_id(resp.result)
    logger.info("telegram.sent_voice", chat_id=chat_id, message_id=new_id)
    return new_id


# ─── helpers ───────────────────────────────────────────────────────────


def _require_media_arg(*, link: str | None, file_id: str | None, kind: str) -> str:
    """Exactly one of link / file_id must be set; return the value to pass."""
    if link and file_id:
        raise ValueError(f"send_{kind}: pass exactly one of `link` or `file_id`")
    if not link and not file_id:
        raise ValueError(f"send_{kind}: must pass one of `link` or `file_id`")
    return link or file_id  # type: ignore[return-value]


def _message_id(result: Any) -> str:
    """Extract message_id as a string (for parity with old WhatsApp flow)."""
    if result is None:
        return ""
    mid = getattr(result, "message_id", None)
    return str(mid) if mid is not None else ""


__all__ = [
    "send_audio",
    "send_document",
    "send_photo",
    "send_text",
    "send_typing",
    "send_voice",
]
